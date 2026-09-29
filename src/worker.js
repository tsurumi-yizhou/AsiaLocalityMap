// 此地 · Asia Locality Map — Cloudflare Worker
// 站点是纯静态的，全部内容在 docs/，由 assets 绑定直接提供。
// 404 与 / → index.html 的处理都交给 assets（html_handling、not_found_handling），
// 这个 Worker 不需要介入任何请求。

export default {
  fetch(request, env) {
    return env.ASSETS.fetch(request);
  },
};
