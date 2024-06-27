module.exports = async ({
                          github,
                          context,
                          require,
                          exec,
                          partial_value,
                          pr_id_key,
                          pr_id_value,
                          ecs_cluster,
                          aws_listener_arn,
                          aws_load_balancer_arn
                        }) => {

  // Needed for aws output
  let output = '';
  const options = {};
  options.listeners = {
    stdout: (data) => {
      output += data.toString();
    },
  };

  // Remove the load balancer stuff first
  // Rules
  await exec.exec(`aws elbv2 describe-rules --listener-arn ${aws_listener_arn} --query "Rules" --output json`, [], options);
  const rules = JSON.parse(output);
  output = '';

  const rule_arns_to_destroy = [];

  for (const listener_rule of rules) {

    // describe doesn't include tags...
    await exec.exec(`aws elbv2 describe-tags --resource-arns ${listener_rule['RuleArn']} --query "TagDescriptions[0].Tags" --output json`, [], options);
    const tags = JSON.parse(output);
    output = '';

    for (const tag of tags) {
      // Look for our PR_ID_KEY, and if we're doing a partial string match, see if PR_ID_VALUE is in value, otherwise do an exact match
      if (tag['Key'] === pr_id_key && ((partial_value && tag['Value'].indexOf(pr_id_value) === 0) || (!partial_value && tag['Value'] === pr_id_value))) {
        rule_arns_to_destroy.push(listener_rule['RuleArn']);
      }
    }

    for (const rule of rule_arns_to_destroy) {
      await exec.exec(`aws elbv2 delete-rule --rule-arn "${rule}"`, [], options);
      output = '';
    }
  }

  // Target groups
  const target_groups_to_destroy = [];

  await exec.exec(`aws elbv2 describe-target-groups --load-balancer-arn ${aws_load_balancer_arn} --query "TargetGroups" --output json`, [], options);
  const target_groups = JSON.parse(output);
  output = '';

  for (const target_group of target_groups) {

    // describe doesn't include tags...
    await exec.exec(`aws elbv2 describe-tags --resource-arns ${target_group['TargetGroupArn']} --query "TagDescriptions[0].Tags" --output json`, [], options);
    const tags = JSON.parse(output);
    output = '';


    for (const tag of tags) {
      // Look for our PR_ID_KEY, and if we're doing a partial string match, see if PR_ID_VALUE is in value, otherwise do an exact match
      if (tag['Key'] === pr_id_key && ((partial_value && tag['Value'].indexOf(pr_id_value) === 0) || (!partial_value && tag['Value'] === pr_id_value))) {
        target_groups_to_destroy.push(target_group['TargetGroupArn']);
      }
    }

    for (const target_group_arn of target_groups_to_destroy) {
      await exec.exec(`aws elbv2 delete-target-group --target-group-arn "${target_group_arn}"`, [], options);
      output = '';
    }
  }
  // --

  // Grab a list of tasks
  await exec.exec(`aws ecs list-tasks --cluster ${ecs_cluster} --query "taskArns" --output json`, [], options);
  const tasks = JSON.parse(output);
  output = '';

  let task_arns_to_destroy = [];

  // Look for tasks created by this PR which are identified by our pr_id_key and pr_id_value
  // There shouldn't ever be more than one task per PR, but y'know just in case...
  for (const task_arn of tasks) {
    await exec.exec(`aws ecs describe-tasks --cluster ${ecs_cluster} --task "${task_arn}" --query "tasks[0].tags" --include TAGS --output json`, [], options);
    const tags = JSON.parse(output);
    output = '';

    for (const tag of tags) {
      // Look for our PR_ID_KEY, and if we're doing a partial string match, see if PR_ID_VALUE is in value, otherwise do an exact match
      if (tag['key'] === pr_id_key && ((partial_value && tag['value'].indexOf(pr_id_value) === 0) || (!partial_value && tag['value'] === pr_id_value))) {
        task_arns_to_destroy.push(task_arn);
        break;
      }
    }
  }

  // Delete them all!
  for (const task_arn of task_arns_to_destroy) {
    await exec.exec(`aws ecs stop-task --cluster ${ecs_cluster} --task "${task_arn}" --output json`, [], options);
    output = '';
  }

  const delete_comments = await require('./.github/scripts/delete-comments.js');
  await delete_comments({github: github, context: context});
};