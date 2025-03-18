module.exports = async ({
                          core,
                          exec,
                          require,
                          task_def_arn_file,
                          cache_file_path,
                          pr_id_key,
                          pr_id_value,
                          ecs_cluster,
                          aws_security_groups,
                          aws_subnets,
                          aws_vpc_id,
                          aws_avail_region,
                          aws_listener_arn,
                          preview_is_secure = '1',
                          preview_host_url = 'preview.thunderbird.dev'
                        }) => {
  const fs = require('fs');
  const {uniqueNamesGenerator, adjectives, colors} = require('unique-names-generator');
  const task_def_arn = await require(task_def_arn_file);

  // Needed for aws output
  let output = '';
  const options = {};
  options.listeners = {
    stdout: (data) => {
      output += data.toString();
    },
  };

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Run an aws command (sleeping in between runs) and wait until condition_callback(value) returns true
   * @param aws_command Command to exec
   * @param condition_callback Callback conditional that we're waiting to return true
   * @param max_wait_s Max wait time in seconds
   * @returns {Promise<null>}
   */
  async function waitFor(aws_command, condition_callback, max_wait_s = 30) {
    let value = null;
    let retry_count = 0;
    output = '';

    // Wait until max_wait_s or until condition_callback is truthy
    while (retry_count < max_wait_s) {
      await exec.exec(aws_command, [], options);
      value = output;
      output = '';

      if (value) {
        value = JSON.parse(value);
      }

      // Check with our callback to see if we've got the goods
      if (condition_callback(value)) {
        break;
      }

      retry_count++;
      await sleep(1000);
    }

    return value;
  }

  // Start a fargate spot task tagged with our PR_ID_KEY/VALUE, under the specified cluster, with networking settings
  // Reference: https://docs.aws.amazon.com/cli/latest/reference/ecs/run-task.html
  await exec.exec(`aws ecs run-task --tags "key=${pr_id_key},value=${pr_id_value}" --cluster ${ecs_cluster} --task-definition ${task_def_arn} --capacity-provider-strategy capacityProvider="FARGATE_SPOT",weight=0,base=0 --network-configuration awsvpcConfiguration={subnets=[${aws_subnets}],securityGroups=[${aws_security_groups}],assignPublicIp="ENABLED"} --query "tasks[0].taskArn" --output json`, [], options);
  const task_arn = JSON.parse(output);
  output = '';

  if (!task_arn) {
    core.setFailed("TaskArn was not found - The fargate instance probably failed to launch!");
    return;
  }

  // Lookup the task we just ran, and wait until the network interface id is available
  // Reference: https://docs.aws.amazon.com/cli/latest/reference/ecs/describe-tasks.html
  const private_ip_array = await waitFor(
      `aws ecs describe-tasks --tasks "${task_arn}" --cluster ${ecs_cluster} --query "tasks[0].attachments[0].details[?name == 'privateIPv4Address'].value" --output json`, (value) => {
        return value && value.length > 0;
      }
  );

  if (!private_ip_array || private_ip_array.length === 0) {
    core.setFailed("Private IP was not found");
    return;
  }

  const private_ip = private_ip_array[0];

  // List of fun bird names
  const bird_names = ["albatross", "cassowary", "chicken", "crane", "condor", "dove", "duck", "emu", "falcon", "flamingo", "frogmouth", "grebe", "hawk", "heron", "hoatzin", "hornbill", "hummingbird", "ibis", "kagu", "kingfisher", "kiwi", "loon", "mesite", "mousebird", "nightjar", "oilbird", "ostrich", "owl", "parrot", "pelican", "penguin", "petrel", "pigeon", "potoo", "quetzal", "rhea", "sandgrouse", "shortbird", "stork", "sunbittern", "swift", "tinamou", "treeswift", "tropicbird", "turaco", "vulture", "wader", "woodpecker"];

  const subdomain = uniqueNamesGenerator({
    dictionaries: [adjectives, colors, bird_names],
    separator: '-',
    length: 3,
  });

  const port = preview_is_secure === '1' ? 443 : 80;
  const protocol = preview_is_secure === '1' ? 'HTTPS' : 'HTTP';

  // Reference: https://docs.aws.amazon.com/cli/latest/reference/elbv2/create-target-group.html
  const target_group_array = await waitFor(
      `aws elbv2 create-target-group --tags "Key=${pr_id_key},Value=${pr_id_value}" --name pe-${subdomain.slice(0, 28)} --protocol ${protocol} --port ${port} --target-type ip --vpc-id ${aws_vpc_id} --output json`, (value) => {
        return value && value !== {};
      }
  );

  if (!target_group_array || target_group_array.length === 0) {
    core.setFailed("Target group could not be created");
    return;
  }

  const target_group = target_group_array['TargetGroups'][0]['TargetGroupArn'] ?? null;

  if (!target_group) {
    core.setFailed("Target group could not be found, but it was created?");
    return;
  }

  // Reference: https://docs.aws.amazon.com/cli/latest/reference/elbv2/register-targets.html
  const target = await waitFor(
      `aws elbv2 register-targets --target-group-arn ${target_group} --targets Id=${private_ip},Port=80,AvailabilityZone=${aws_avail_region} --output json`, (value) => {
        // There's no output for this
        return true;
      }
  );


  // Grab all of the fules
  await exec.exec(`aws elbv2 describe-rules --listener-arn ${aws_listener_arn} --query "Rules" --output json`, [], options);
  const rules = JSON.parse(output);
  output = '';

  // We need to find a unique priority. The number doesn't matter because it we have custom matching rules on it..
  let priority = 5;
  const priorities = [];
  for (const rule of rules) {
    priorities.push(rule['Priority']);
  }

  // Uh...replace this with something nicer
  for (let i = 2; i < 1000; i++) {
    if (priorities.indexOf(`${i}`) === -1) {
      priority = i;
      break;
    }
  }

  const conditions = `Field=host-header,HostHeaderConfig={"Values"=["${subdomain}.${preview_host_url}"]}`;
  const actions = `Type=forward,TargetGroupArn=${target_group}`;
  const rule = await waitFor(
      `aws elbv2 create-rule --tags "Key=${pr_id_key},Value=${pr_id_value}" --listener-arn ${aws_listener_arn} --priority ${priority} --conditions ${conditions} --actions ${actions} --output json`, (value) => {
        return !!value && value !== 'None';
      }
  );

  // Write the url to file, so we can cache it between jobs
  fs.writeFileSync(cache_file_path, JSON.stringify(`${protocol.toLowerCase()}://${subdomain}.${preview_host_url}`));
}
