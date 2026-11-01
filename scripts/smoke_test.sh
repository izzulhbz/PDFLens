#!/usr/bin/env sh
# Smoke test for a running stack (docker compose up): talks to it over HTTP
# the way a browser would, through Nginx. Needs no Ollama models.
#
#   ./scripts/smoke_test.sh [base_url]     (default http://127.0.0.1:8080)
#
# Creates a throwaway account. Exits non-zero on the first failed check.
set -eu

BASE="${1:-http://127.0.0.1:8080}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
JAR="$WORK/cookies.txt"
EMAIL="smoke-$(date +%s)-$$@example.com"
PASSWORD="smoke-test-password-$$-$(date +%s)"

pass() { echo "ok   $1"; }
fail() { echo "FAIL $1"; exit 1; }

# status METHOD PATH [curl args...]: print only the HTTP status code.
status() {
  method="$1"; path="$2"; shift 2
  curl -s -o "$WORK/body" -w "%{http_code}" -X "$method" "$BASE$path" "$@"
}

echo "Waiting for $BASE ..."
i=0
until [ "$(status GET /api/health)" = "200" ]; do
  i=$((i + 1))
  [ "$i" -ge 60 ] && fail "the stack didn't become healthy"
  sleep 2
done
pass "API is up"

status GET /api/health/ready >/dev/null
grep -q '"database":"ok"' "$WORK/body" || fail "database not ready: $(cat "$WORK/body")"
pass "database reachable with pgvector"

headers="$(curl -sI "$BASE/")"
echo "$headers" | grep -qi "^content-security-policy: default-src 'self'" || fail "app has no CSP"
echo "$headers" | grep -qi "^server: nginx/" && fail "Nginx reveals its version"
pass "app served with CSP, Nginx version hidden"

curl -sI "$BASE/api/health" | grep -qi "^x-content-type-options: nosniff" || fail "API has no nosniff"
pass "API security headers"

[ "$(status GET /api/documents)" = "401" ] || fail "documents readable without logging in"
pass "login required"

body="{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}"
code="$(status POST /api/auth/register -H "Content-Type: application/json" --data "$body")"
[ "$code" = "403" ] || fail "register without the CSRF header gave $code, not 403"
pass "CSRF header required"

code="$(status POST /api/auth/register -c "$JAR" -H "X-PDFLens-CSRF: 1" \
  -H "Content-Type: application/json" --data "$body")"
[ "$code" = "201" ] || fail "register gave $code: $(cat "$WORK/body")"
[ "$(status GET /api/auth/me -b "$JAR")" = "200" ] || fail "new session not accepted"
pass "register and session"

# A copy of the cookie, as if stolen, must stop working once the user logs out.
cp "$JAR" "$WORK/stolen.txt"
[ "$(status POST /api/auth/logout -b "$JAR" -c "$JAR" -H "X-PDFLens-CSRF: 1")" = "204" ] \
  || fail "logout failed"
[ "$(status GET /api/auth/me -b "$WORK/stolen.txt")" = "401" ] \
  || fail "a copy of the cookie still works after logout"
pass "logout revokes copies of the session cookie"

echo "All smoke checks passed."
