#!/usr/bin/env python3
"""
겸손몰 후기 분석 — Publish 서버 (localhost:7878)

  GET  /         → 대시보드 HTML 서빙 (file:// 없이 바로 접속 가능)
  POST /publish  → groups.json + data.json 저장 + deploy_nas.py + Cloudflare 업로드

run_crawler.command 실행 시 자동으로 백그라운드에서 시작됩니다.
"""

import json, subprocess, os, sys, shutil
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 7878
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD   = os.path.join(SCRIPT_DIR, "겸손몰 후기 분석.html")

# .env 로드 (python-dotenv 없어도 동작)
def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
    except ImportError:
        env_path = os.path.join(SCRIPT_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()


# ── Cloudflare Pages 업로드 ──────────────────────────
def deploy_to_cloudflare():
    """빌드된 HTML을 Cloudflare Pages에 업로드 (npx wrangler 사용)"""
    account_id = os.environ.get("CF_ACCOUNT_ID", "").strip()
    api_token  = os.environ.get("CF_API_TOKEN", "").strip()
    project    = os.environ.get("CF_PROJECT", "").strip()

    if not all([account_id, api_token, project]):
        return None, None  # 미설정 → 조용히 스킵

    if not os.path.exists(DASHBOARD):
        return False, "대시보드 파일 없음"

    deploy_dir = os.path.join(SCRIPT_DIR, ".cf_deploy")
    try:
        os.makedirs(deploy_dir, exist_ok=True)
        shutil.copy(DASHBOARD, os.path.join(deploy_dir, "index.html"))
        # Cloudflare Function(functions/api/publish.js) 포함
        src_fn = os.path.join(SCRIPT_DIR, "functions")
        if os.path.isdir(src_fn):
            dst_fn = os.path.join(deploy_dir, "functions")
            shutil.rmtree(dst_fn, ignore_errors=True)
            shutil.copytree(src_fn, dst_fn)

        env = {
            **os.environ,
            "CLOUDFLARE_API_TOKEN":  api_token,
            "CLOUDFLARE_ACCOUNT_ID": account_id,
        }
        proc = subprocess.run(
            ["npx", "--yes", "wrangler@3", "pages", "deploy", deploy_dir,
             f"--project-name={project}", "--commit-dirty=true", "--branch=main"],
            capture_output=True, text=True, cwd=SCRIPT_DIR, env=env,
            timeout=120
        )
        ok = proc.returncode == 0
        msg = proc.stdout[-400:] if ok else proc.stderr[-400:]
        return ok, msg
    except FileNotFoundError:
        return False, "npx를 찾을 수 없습니다. Node.js가 설치되어 있는지 확인하세요."
    except Exception as e:
        return False, str(e)
    finally:
        shutil.rmtree(deploy_dir, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):

    # ── GET: 대시보드 HTML 서빙 ──────────────────────
    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            target = DASHBOARD if os.path.exists(DASHBOARD) \
                     else os.path.join(SCRIPT_DIR, "index.html")
            try:
                with open(target, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    # ── OPTIONS: CORS preflight ──────────────────────
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    # ── POST /publish ────────────────────────────────
    def do_POST(self):
        if self.path != "/publish":
            self.send_response(404)
            self.end_headers()
            return
        try:
            n    = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))
            saved = []

            # groups.json 저장
            if body.get("groups") is not None:
                p = os.path.join(SCRIPT_DIR, "groups.json")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(body["groups"], f, ensure_ascii=False, indent=2)
                saved.append(f"groups.json ({len(body['groups'])}개 그룹)")

            # data.json 저장 (relabels 병합 완료본)
            if body.get("data") is not None:
                p = os.path.join(SCRIPT_DIR, "data.json")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(body["data"], f, ensure_ascii=False, indent=2)
                saved.append(f"data.json ({len(body['data'].get('reviews', {}))}건)")

            print(f"  💾 {', '.join(saved)}")
            print("  ▶ deploy_nas.py 실행 중...")

            proc = subprocess.run(
                [sys.executable, os.path.join(SCRIPT_DIR, "deploy_nas.py")],
                capture_output=True, text=True, cwd=SCRIPT_DIR
            )
            ok = proc.returncode == 0
            print(f"  {'✅' if ok else '❌'} deploy {'완료' if ok else '실패'}")
            if not ok:
                print(f"     {proc.stderr[:300]}")

            # Cloudflare Pages 업로드 (CF 환경변수 있을 때만)
            cf_ok = cf_url = None
            if ok and os.environ.get("CF_API_TOKEN"):
                print("  ▶ Cloudflare Pages 배포 중...")
                project = os.environ.get("CF_PROJECT", "").strip()
                cf_ok, cf_msg = deploy_to_cloudflare()
                if cf_ok is None:
                    print("  ℹ️  Cloudflare 미설정 — 건너뜀")
                elif cf_ok:
                    cf_url = f"https://{project}.pages.dev"
                    print(f"  ✅ Cloudflare 배포 완료: {cf_url}")
                else:
                    print(f"  ⚠️  Cloudflare 배포 실패: {cf_msg[:100]}")

            self._json(200, {
                "ok":     ok,
                "saved":  saved,
                "output": proc.stdout[-600:],
                "error":  proc.stderr[-300:] if not ok else "",
                "cf_ok":  cf_ok,
                "cf_url": cf_url,
            })

        except Exception as e:
            print(f"  ❌ 오류: {e}")
            self._json(500, {"ok": False, "error": str(e)})

    # ── 헬퍼 ────────────────────────────────────────
    def _cors(self):
        origin = self.headers.get("Origin") or "*"
        self.send_header("Access-Control-Allow-Origin",  origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Vary", "Origin")

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    os.chdir(SCRIPT_DIR)
    cf_set = bool(os.environ.get("CF_API_TOKEN"))
    print("=" * 55)
    print("🌐 겸손몰 후기 분석 — Publish 서버")
    print(f"   주소: http://localhost:{PORT}")
    print(f"   폴더: {SCRIPT_DIR}")
    print(f"   Cloudflare: {'✅ 설정됨' if cf_set else '⚠️  미설정 (.env에 CF_* 추가)'}")
    print("   종료: Ctrl+C")
    print("=" * 55)
    try:
        HTTPServer(("localhost", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n👋 서버 종료")
