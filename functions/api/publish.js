// Cloudflare Pages Function — POST /api/publish
//
// 브라우저의 Publish 버튼이 보낸 { groups, data }를 받아
// GitHub에 data.json + groups.json을 단일 커밋으로 push 한다.
// push 가 build_deploy 워크플로우를 트리거 → 빌드 + 재배포.
//
// 필요한 환경변수 (Cloudflare Pages → Settings → Environment variables):
//   GH_TOKEN  : GitHub Personal Access Token (contents: write)
//   GH_REPO   : "withqnx/withqnx"
//   GH_BRANCH : "main"  (선택, 기본 main)
//   PUBLISH_PWD : 관리자 비밀번호 (선택, 설정 시 일치해야 커밋)

const GH = "https://api.github.com";

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

async function gh(path, token, init = {}) {
  const res = await fetch(`${GH}${path}`, {
    ...init,
    headers: {
      "Authorization": `Bearer ${token}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "nonohumble-publish",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`GitHub ${path} → ${res.status}: ${txt.slice(0, 200)}`);
  }
  return res.json();
}

export async function onRequestPost({ request, env }) {
  try {
    const token  = env.GH_TOKEN;
    const repo   = env.GH_REPO || "withqnx/withqnx";
    const branch = env.GH_BRANCH || "main";

    if (!token) {
      return json({ ok: false, error: "서버에 GH_TOKEN이 설정되지 않았습니다." }, 500);
    }

    const body = await request.json();

    // (선택) 비밀번호 검증
    if (env.PUBLISH_PWD && body.pwd !== env.PUBLISH_PWD) {
      return json({ ok: false, error: "비밀번호가 일치하지 않습니다." }, 403);
    }

    // 커밋할 파일 모으기
    const files = [];
    if (body.groups !== undefined && body.groups !== null) {
      files.push({ path: "groups.json", content: JSON.stringify(body.groups, null, 2) });
    }
    if (body.data !== undefined && body.data !== null) {
      files.push({ path: "data.json", content: JSON.stringify(body.data, null, 2) });
    }
    if (!files.length) {
      return json({ ok: false, error: "저장할 내용이 없습니다." }, 400);
    }

    // ── Git Data API로 단일 커밋 만들기 ──
    // 1) 최신 ref
    const ref = await gh(`/repos/${repo}/git/ref/heads/${branch}`, token);
    const latestCommitSha = ref.object.sha;

    // 2) base tree
    const commit = await gh(`/repos/${repo}/git/commits/${latestCommitSha}`, token);
    const baseTreeSha = commit.tree.sha;

    // 3) blobs
    const treeItems = [];
    for (const f of files) {
      // base64 대신 utf-8 원문을 그대로 보낸다.
      // 이전 base64 변환 함수는 바이트를 하나씩 문자열에 이어붙였는데(수백만 회),
      // data.json 이 6MB 대로 커지면서 Worker CPU/메모리 한도를 초과했다.
      // 한도 초과는 catch 로 잡히지 않아 Cloudflare 가 HTML 에러 페이지를 반환하고,
      // 프론트에서는 "Unexpected token '<' ... is not valid JSON" 으로 보였다.
      const blob = await gh(`/repos/${repo}/git/blobs`, token, {
        method: "POST",
        body: JSON.stringify({ content: f.content, encoding: "utf-8" }),
      });
      treeItems.push({ path: f.path, mode: "100644", type: "blob", sha: blob.sha });
    }

    // 4) tree
    const tree = await gh(`/repos/${repo}/git/trees`, token, {
      method: "POST",
      body: JSON.stringify({ base_tree: baseTreeSha, tree: treeItems }),
    });

    // 5) commit
    const names = files.map(f => f.path).join(", ");
    const newCommit = await gh(`/repos/${repo}/git/commits`, token, {
      method: "POST",
      body: JSON.stringify({
        message: `📝 Publish: ${names}`,
        tree: tree.sha,
        parents: [latestCommitSha],
      }),
    });

    // 6) ref 업데이트
    await gh(`/repos/${repo}/git/refs/heads/${branch}`, token, {
      method: "PATCH",
      body: JSON.stringify({ sha: newCommit.sha, force: false }),
    });

    return json({
      ok: true,
      saved: files.map(f => f.path),
      commit: newCommit.sha.slice(0, 7),
      message: "GitHub에 저장 완료. 1~2분 후 모든 사람에게 반영됩니다.",
    });

  } catch (e) {
    return json({ ok: false, error: String(e.message || e) }, 500);
  }
}

// CORS preflight (file:// 로컬 테스트 대비)
export async function onRequestOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
