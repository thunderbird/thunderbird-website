module.exports = async ({github, context}) => {

  const response_data = await github.paginate(github.rest.issues.listComments, {
        issue_number: context.payload.number, // Pr number
        owner: context.repo.owner,
        repo: context.repo.repo,
      }
  );

  if (response_data) {
    for (const comment of response_data) {
      // Find the bots previous comments
      if (comment.user.login === 'github-actions[bot]' && comment.body.indexOf('preview environments') !== -1) {
        // If we have an existing comment, delete it
        // Reference: https://octokit.github.io/rest.js/v19#issues-delete-comment
        github.rest.issues.deleteComment({
          comment_id: comment.id,
          issue_number: context.payload.number, // Pr number
          owner: context.repo.owner,
          repo: context.repo.repo,
        });
      }
    }
  }

};