module.exports = async ({core, github, context, require, website_url_file, start_page_url_file}) => {
  let website_url = null;
  let start_page_url = null;
  try {
    website_url = await require(website_url_file);
  } catch {
    // Ignore
  }
  try {
    start_page_url = await require(start_page_url_file);
  } catch {
    // Ignore
  }

  if (!website_url && !start_page_url) {
    core.setFailed("No urls to post!");
    return;
  }

  // Plural depending on if we have both urls available.
  const messages = [
    website_url && start_page_url ? 'Your preview environments have been started and will be available shortly at:' :
      'Your preview environment has started and will be available shortly at:'
  ];

  if (website_url) {
    messages.push(`thunderbird.net: ${website_url}`);
  }
  if (start_page_url) {
    messages.push(`start.thunderbird.net: ${start_page_url}`);
  }

  // Add a check that succeeds with output url :)
  // Reference: https://octokit.github.io/rest.js/v19#issues-create-comment
  github.rest.issues.createComment({
    issue_number: context.payload.number, // Pr number
    owner: context.repo.owner,
    repo: context.repo.repo,
    body: messages.join('\n')
  });
};
