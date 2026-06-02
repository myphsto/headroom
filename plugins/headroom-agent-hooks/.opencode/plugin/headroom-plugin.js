/**
 * Headroom plugin for OpenCode
 * Ensures the Headroom compression proxy is running before tool execution.
 */
export const HeadroomPlugin = async ({ project, client, $, directory, worktree }) => {
  const HEADROOM_MARKER = "headroom-init-opencode";
  let proxyStarted = false;

  async function ensureHeadroomRunning() {
    if (proxyStarted) return;

    try {
      const healthCheck = await $`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8787/readyz`
        .nothrow()
        .timeout(3000);

      if (healthCheck.stdout.trim() === "200") {
        proxyStarted = true;
        return;
      }
    } catch {
      // Health check failed, try to start headroom
    }

    try {
      await $`headroom init hook ensure --marker ${HEADROOM_MARKER}`
        .nothrow()
        .timeout(15000);
      proxyStarted = true;
    } catch (err) {
      await client.app.log({
        body: {
          service: "headroom-plugin",
          level: "debug",
          message: "Failed to ensure headroom proxy: " + (err.message || err),
        },
      });
    }
  }

  return {
    "session.created": async () => {
      await ensureHeadroomRunning();
      await client.app.log({
        body: {
          service: "headroom-plugin",
          level: "info",
          message: "Headroom plugin initialized",
          extra: { project: project?.name, directory },
        },
      });
    },

    "tool.execute.before": async (input, output) => {
      if (input.tool === "bash" || input.tool === "shell") {
        await ensureHeadroomRunning();
      }
    },

    "shell.env": async (input, output) => {
      output.env.HEADROOM_MARKER = HEADROOM_MARKER;
      output.env.HEADROOM_PROJECT_DIR = input.cwd || directory;
    },
  };
};
