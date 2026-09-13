/**
 * 市場AI秘書 — 業種別ランキング用 CORSプロキシ（Cloudflare Worker）
 *
 * 役割: ブラウザから Yahoo Finance のデータを直接取得できるよう、
 *       CORSヘッダを付けて中継するだけの軽量プロキシ。
 *       （ザラ場中の業種別ランキングをリアルタイム更新するために使う）
 *
 * セキュリティ: 中継先は finance.yahoo.com のみに限定（オープンプロキシ化を防止）。
 *
 * デプロイ手順は SETUP_CLOUDFLARE.md を参照。
 * デプロイ後の URL（https://xxxx.workers.dev）を GitHub Secrets の
 * CF_PROXY_URL に登録すれば、レポートが自動でこのプロキシを使います。
 */
export default {
  async fetch(request) {
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "*",
      "Cache-Control": "no-store",
    };

    // プリフライト
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors });
    }

    const url = new URL(request.url);
    const target = url.searchParams.get("url");
    if (!target) {
      return new Response(JSON.stringify({ error: "missing url param" }), {
        status: 400,
        headers: { ...cors, "Content-Type": "application/json" },
      });
    }

    // 中継先を Yahoo Finance に限定（セキュリティ）
    let t;
    try {
      t = new URL(target);
    } catch (e) {
      return new Response(JSON.stringify({ error: "bad url" }), {
        status: 400,
        headers: { ...cors, "Content-Type": "application/json" },
      });
    }
    if (!/(^|\.)finance\.yahoo\.com$/.test(t.hostname)) {
      return new Response(JSON.stringify({ error: "forbidden host" }), {
        status: 403,
        headers: { ...cors, "Content-Type": "application/json" },
      });
    }

    try {
      const resp = await fetch(target, {
        headers: { "User-Agent": "Mozilla/5.0" },
        cf: { cacheTtl: 0 },
      });
      const body = await resp.text();
      return new Response(body, {
        status: resp.status,
        headers: { ...cors, "Content-Type": "application/json" },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: "fetch failed" }), {
        status: 502,
        headers: { ...cors, "Content-Type": "application/json" },
      });
    }
  },
};
