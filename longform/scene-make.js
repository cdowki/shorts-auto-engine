// scene-make.js — 블로그 글 1편 → 긴 영상 장면표(scenes.json) 자동 작성 (쇼츠창 2026-11-03)
//
// 실행 (C:\shorts-clip\longform 에서)
//   node scene-make.js --id 20261103_r1
//   node scene-make.js --id 20261103_r1 --short-file 숏폼대본.txt --short-title "쇼츠 제목"   (숏폼 장면표도 같이)
//   node scene-make.js --id 20261103_r1 --dry        (클로드에 보낼 질문만 파일로 저장하고 끝)
//   node scene-make.js --job jobs/20261105_r1/job.json   (서버용 11/4 — 본문·제목을 GAS가 준 작업 파일에서 읽음)
//
// 재료 (읽기만 함)
//   본문  C:\assetflow\gen_<번호>.txt
//   제목  C:\assetflow\temp-images\<번호>\title.txt
//   (서버) --job 파일: { postId, blogTitle, body } — run_daily.js가 GAS longform_jobs(with_body)에서 받아 만듦
// 결과
//   jobs\<번호>\scenes.json  (+ short.json)   · 기록 logs\scene_<시각>.txt
//   jobs\<번호>\img\scene_NN.png — 창고에서 고른 그림을 복사(그림을 새로 그리지 않음, 11/4~)
//
// 그림 고르기 (11/4 비광도기님 승인 — 긴영상_설계와_인수인계 9절)
//   창고목록.json 에서 장면마다 그림 번호(img)를 고르고, 원했던 그림(want)·맞는 정도(match: 딱맞음/비슷함/대체)를 적게 함
//   검사: 창고에 있는 번호 · 한 영상 안 같은 그림 두 번 금지 · 바로 앞 3편(약 하루)에 쓴 그림 금지 · 부부 그림 2~4장 · 칠판 그림 2장까지
//         · 글 제목과 낱말이 겹치는 주제 그림(예: 펫보험 → 강아지·고양이)이 있으면 1장 이상 (11/4 추가)
//   기록: 창고_사용기록.json(글마다 쓴 그림) · 창고_부족기록.json(match가 "대체"인 장면 — 18시 점검이 읽을 곳)
//
// 클로드 부르는 법 — AssetFlow `_claude-generate.js`와 같은 잠금 (운영 창 10/8 실측 방식)
//   구독(claude -p) · API 키 두 개를 지운 환경 · 빈 폴더에서 · 도구 0개 · 시작 정보로 구독/도구 0개 확인 뒤 진행
//   모델 소네트(구독 사용량 아끼기). 검사에 걸리면 무엇이 틀렸는지 알려 주고 다시 쓰게 함(최대 3번)
//
// 장면표 규칙: 2026-11-03 비광도기님 승인 (긴영상_설계와_인수인계)

'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const HERE = __dirname;
const argv = process.argv.slice(2);
const pickArg = (name, def) => {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] !== undefined && !argv[i + 1].startsWith('--') ? argv[i + 1] : def;
};
const JOB_FILE = pickArg('--job', null);
const JOB = (() => {
  if (!JOB_FILE) return null;
  try { return JSON.parse(fs.readFileSync(path.resolve(JOB_FILE), 'utf8').replace(/^\uFEFF/, '')); } catch (e) { return { bad: e.message }; }
})();
const ID = pickArg('--id', JOB && JOB.postId ? String(JOB.postId) : null);
const ASSETFLOW = pickArg('--assetflow', 'C:\\assetflow');
const MODEL = pickArg('--model', 'sonnet');
const SHORT_FILE = pickArg('--short-file', null);
const SHORT_TITLE = pickArg('--short-title', '');
const DRY = argv.includes('--dry');
const MAX_TRIES = 3;
const TRY_TIMEOUT_MS = 8 * 60 * 1000;
const WORK_DIR = path.join(HERE, 'claude-empty');
const KNOWN_MCP_SERVERS = [
  'chrome-devtools', 'playwright', 'claude_ai_Claude_Docs', 'claude_ai_Gmail',
  'claude_ai_Google_Drive', 'claude_ai_Google_Sheets', 'claude_ai_Notion',
];
const REF_SOLO = '43_발표_그래프.png';
const REF_COUPLE = '49_연금_통장확인.png';
const CATALOG_FILE = path.join(HERE, '창고목록.json');
const USED_FILE = path.join(HERE, '창고_사용기록.json');
const SHORTAGE_FILE = path.join(HERE, '창고_부족기록.json');
const BAN_RECENT_POSTS = 3;   // 바로 앞 이만큼의 글(다른 글)에 쓴 그림은 못 고름 — 하루 3편 기준 약 하루
const SOFT_DAYS = 5;          // 이 기간에 쓴 그림은 되도록 피하라고만 알림(창고 149장 ÷ 하루 약 30장이라 5일 전부 막으면 모자람)
const MATCHES = ['딱맞음', '비슷함', '대체'];

// ── 창고 ─────────────────────────────────────────
function readJson(file, def) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '')); } catch (e) { return def; }
}
function loadCatalog() {
  const c = readJson(CATALOG_FILE, null);
  if (!c || !Array.isArray(c.items)) return null;
  const usable = c.items.filter((x) => x.file);
  return { all: c.items, usable, byId: Object.fromEntries(usable.map((x) => [x.id, x])) };
}
function loadUsed() { const u = readJson(USED_FILE, []); return Array.isArray(u) ? u : []; }
function recentBans(used, postId) {
  // 다른 글들 중 가장 최근 BAN_RECENT_POSTS편이 쓴 그림 → 금지 / SOFT_DAYS일 안에 쓴 그림 → 피하기
  const others = used.filter((u) => u.post !== postId).sort((a, b) => String(b.made).localeCompare(String(a.made)));
  const hard = new Set();
  others.slice(0, BAN_RECENT_POSTS).forEach((u) => (u.ids || []).forEach((i) => hard.add(i)));
  const cut = Date.now() - SOFT_DAYS * 86400000;
  const soft = new Set();
  others.filter((u) => Date.parse(u.madeIso || '') >= cut).forEach((u) => (u.ids || []).forEach((i) => { if (!hard.has(i)) soft.add(i); }));
  return { hard, soft };
}
// 글 제목과 낱말이 겹치는 주제 그림(공통 동작·부부·시작/마무리 묶음 제외) — 11/4 펫보험 시험에서 강아지·고양이를 안 고른 뒤 추가
const TOPIC_STOP = new Set('비교 확인 기준 정리 신청 조회 가입 계산 금액 매달 시작 질문 궁금 고민 설명 핵심 중요 마무리 감사 인사 생활 방법 혜택 지원 대상 제도 변화 발표 소식 뉴스 체크 점검 목록 안내 준비 결론 정답 깨달음 오해 알아보기 살펴보기 다음에 남겨주세요 아래 댓글 구독 축하 좋은 확대 따져보기 유리 불리 일정 언제 시행 기한 날짜 기간 마감 건강 갱신 이전 은퇴'.split(' '));
function topicCandidates(cat, title, bans) {
  return cat.usable.filter((x) => !/^[ABL]/.test(x.id) && !bans.hard.has(x.id)
    && (x.tags || []).some((t) => t.length >= 2 && !TOPIC_STOP.has(t) && String(title).includes(t)));
}
function catalogGuide(cat, bans) {
  const lines = cat.usable.map((x) => {
    const mark = [x.couple ? '부부' : '혼자', x.board ? '칠판' : ''].filter(Boolean).join('·');
    const flag = bans.hard.has(x.id) ? ' [금지:최근 사용]' : bans.soft.has(x.id) ? ' [되도록 피함]' : '';
    return `${x.id} ${x.name} (${mark}) — ${x.tags.join(' ')}${flag}`;
  });
  return `[그림 창고 — 장면마다 아래 번호 중 하나를 img 칸에 씀. 그림은 새로 그리지 않음]\n${lines.join('\n')}`;
}

// ── 기록 ─────────────────────────────────────────
function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}
const RUN = stamp();
const LOG_DIR = path.join(HERE, 'logs');
if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
const RUN_LOG = path.join(LOG_DIR, `scene_${RUN}.txt`);
function log(...a) {
  const line = a.join(' ');
  console.log(line);
  try { fs.appendFileSync(RUN_LOG, `${line}\r\n`, 'utf8'); } catch (e) { /* 무시 */ }
}

// ── 장면표 규칙 (클로드에게 주는 질문) ───────────────────
const TEMPLATE_GUIDE = `[도표 틀 13가지 — chart 칸에 아래 모양 중 하나를 그대로 씀. 글자 수는 화면 크기 때문에 지켜야 함]
1. {"type":"체크목록","title":"(선택, 20자 이하)","items":["항목(16자 이하)", … 2~4개]} — 확인할 것·할 일·조건
2. {"type":"숫자강조","title":"(선택)","cards":[{"label":"이름(8자 이하)","value":"숫자+단위(9자 이하)","hl":true(강조할 1장만, 선택)}, … 1~4장]} — 핵심 숫자
3. {"type":"단계흐름","title":"(선택)","steps":["단계(10자 이하)", … 3~5개]} — 순서·절차
4. {"type":"나란히비교","title":"(선택)","cols":[{"head":"제목(10자 이하)","lines":["설명(14자 이하)", … 1~3줄]}, … 2~3개]} — 둘·셋 견주기
5. {"type":"조건분기","root":"기준(10자 이하)","warn":true(주의일 때, 선택),"left":{"if":"조건(14자 이하)","then":"결과(12자 이하)"},"right":{"if":"…","then":"…"}} — 한 기준이 두 갈래로
6. {"type":"큰제목","lines":["첫 줄(12자 이하)","둘째 줄(12자 이하)"]} — 주제·당부
7. {"type":"타임라인","title":"(선택)","points":[{"when":"시점(8자 이하)","what":"일(10자 이하)","hl":true(선택)}, … 2~4개]} — 날짜·기간
8. {"type":"짝짓기목록","title":"(선택)","rows":[["항목(8자 이하)","값·결과(12자 이하)"], … 2~4줄]} — 항목마다 값
9. {"type":"항목나열","title":"(선택)","chips":["이름(8자 이하)", … 3~7개],"result":"(선택, 16자 이하)"} — 같은 종류 늘어놓기
10. {"type":"막대비교","title":"(선택)","bars":[{"label":"이름(6자 이하)","value":숫자,"unit":"%"(또는 "만 원" 등),"hl":true(선택)}, … 2~5개],"note":"(선택, 24자 이하)"} — 숫자 크기 견주기. value는 따옴표 없는 숫자
11. {"type":"포함제외","title":"(선택)","in_head":"해당·보장 등(선택)","out_head":"제외·빠짐 등(선택)","in":["(14자 이하)", … 1~4개],"out":["…", … 1~4개]} — 되는 것/안 되는 것
12. {"type":"계산식","title":"(선택)","terms":[{"label":"(6자 이하)","value":"숫자+단위"}, … 2~3개],"ops":["−" 또는 "+" 또는 "×"],"result":{"label":"(6자 이하)","value":"숫자+단위"}} — A ○ B = C
13. {"type":"누적막대","title":"(선택)","parts":[{"label":"(6자 이하)","value":숫자,"unit":"%"}, … 2~3개],"note":"(선택, 20자 이하)"} — 전체를 나눈 몫`;

function buildPrompt(title, body, retryNote, guide, topics) {
  return `너는 5060 세대를 위한 생활 금융·제도 설명 유튜브 영상의 장면표를 쓰는 작가야.
아래 [블로그 본문]만 근거로, 세로 영상 1편의 장면표를 JSON 하나로만 답해줘. JSON 밖에는 아무 글자도 쓰지 마.

[영상 규칙]
- 장면 9~11개. 대사(narration) 합계 650~900자(공백 포함). 장면당 대사 50~110자, 1~2문장.
- 1장면: 주제를 질문으로 던짐. chart는 "큰제목"(영상 제목을 2줄로).
- 2장면: 본문 첫 결론 문단을 요약(숫자가 있으면 "숫자강조").
- 3~8장면: 본문 소제목(##) 구간마다 2장면씩 순서대로. 구간 내용에 가장 맞는 도표 틀을 고름.
- 마지막 장면: 정리. chart는 "체크목록" 또는 "큰제목". 대사 끝은 "궁금한 점은 댓글로 남겨 주세요" 같은 댓글 한 문장.
- 대사는 존댓말, 귀로 듣기 쉬운 짧은 문장. 긴 문장은 쉼표(,)로 끊고, 쉼표·마침표 사이 한 구절은 32자 이하.
- 숫자는 아라비아 숫자로(예: 30%, 3만 원, 1년). 본문에 없는 숫자·날짜·기관명·전화번호는 대사와 도표 어디에도 넣지 마. 본문 숫자를 더하거나 빼서 새 숫자를 만들어야 하면 계산식 틀에만 쓰고, 그 계산이 정확해야 함.
- 연도·날짜는 본문 표기 그대로 써(예: 2024년, 2027년 4월 21일). "24~26년"처럼 연도를 줄이거나 "2027.4.21"·"2026.10"처럼 점으로 쓰지 마. 범위도 "2024~2026년"처럼 앞뒤 모두 네 자리로.
- 본문에 없는 내용, 지어낸 경험담("저도 해 봤는데"), 투자·상품 가입 권유, 단정적 수익 약속은 금지.
- 마크다운 기호(**, ==, ##)는 쓰지 마.

[그림 규칙 — img·want·match 칸]
- 그림은 아래 [그림 창고]에서 고름. 장면 대사에 가장 맞는 번호 하나를 img에 씀(예: "E06").
- want: 이 장면에 원래 가장 어울리는 그림을 한 줄로(30자 이하, 예: "할아버지가 약 봉투를 들고 걱정"). 창고에 없어도 솔직하게 씀.
- match: 고른 그림이 want와 얼마나 맞는지 — "딱맞음"(거의 같음) / "비슷함"(주제·동작이 통함) / "대체"(마땅한 그림이 없어 가장 가까운 것을 씀). 부풀리지 말고 정직하게.
- 한 영상 안에서 같은 번호를 두 번 쓰지 마. "[금지:최근 사용]" 표시 번호는 쓰지 마. "[되도록 피함]" 번호는 다른 마땅한 그림이 없을 때만.
${topics && topics.length ? `- 이 글 주제 그림 후보: ${topics.map((x) => `${x.id} ${x.name}`).join(', ')} — 1장면을 포함해 1~2장은 이 후보 중에서 고름(보는 사람이 그림만 보고도 주제를 알게).\n` : ''}- "부부" 그림을 2~4장 섞음. "칠판" 그림은 2장까지이고, 칠판 그림을 쓴 장면에만 "board":"내림막대" 또는 "오름막대"(내용이 줄어드는지 늘어나는지)를 넣음.

${TEMPLATE_GUIDE}

${guide}

[답 모양]
{"title":"영상 제목(40자 이하, 질문형 가능)","scenes":[{"no":1,"img":"A02","want":"…","match":"딱맞음","chart":{…},"narration":"…"}, …]}
${retryNote ? `\n[지난 답에서 고칠 것 — 반드시 모두 고쳐서 처음부터 다시 써줘]\n${retryNote}\n` : ''}
[블로그 제목]
${title}

[블로그 본문]
${body}
`;
}

// ── 클로드 구독 한 번 부르기 (AssetFlow와 같은 잠금) ─────────
function killTree(child) {
  if (process.platform === 'win32') {
    try { spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true }); } catch (e) { /* 무시 */ }
  } else {
    try { process.kill(-child.pid, 'SIGKILL'); } catch (e) { /* 무시 */ }
  }
}
function cleanEnv() {
  const env = { ...process.env };
  delete env.ANTHROPIC_API_KEY;
  delete env.ANTHROPIC_AUTH_TOKEN;
  return env;
}
function runClaude(prompt) {
  return new Promise((resolve) => {
    if (!fs.existsSync(WORK_DIR)) fs.mkdirSync(WORK_DIR);
    const args = [
      '-p', '--output-format', 'stream-json', '--verbose', '--max-turns', '3', '--model', MODEL,
      '--tools', '""', '--strict-mcp-config', '--disable-slash-commands', '--permission-prompts', 'none',
      '--disallowedTools', KNOWN_MCP_SERVERS.map((s) => `mcp__${s}`).join(','),
    ];
    const started = Date.now();
    const child = spawn('claude', args, { cwd: WORK_DIR, env: cleanEnv(), shell: true, windowsHide: true, detached: process.platform !== 'win32' });
    let out = '';
    let err = '';
    let pending = '';
    let init = null;
    let result = null;
    let lockProblem = '';
    const handle = (line) => {
      const t = line.trim();
      if (!t.startsWith('{')) return;
      let o;
      try { o = JSON.parse(t); } catch (e) { return; }
      if (o.type === 'system' && o.subtype === 'init' && !init) {
        init = o;
        const tools = Array.isArray(o.tools) ? o.tools : [];
        if (tools.length > 0) {
          lockProblem = `도구 ${tools.length}개가 열려 있음 (${tools.slice(0, 8).join(', ')})`;
          killTree(child);
        } else if (o.apiKeySource && o.apiKeySource !== 'none') {
          lockProblem = `구독이 아닌 인증(${o.apiKeySource})으로 시작함 — API 요금이 나갈 수 있어 멈춤`;
          killTree(child);
        } else {
          log(`  [잠금] 열린 도구 0개 ✓ / 인증 ${o.apiKeySource} / 모델 ${o.model}`);
        }
      }
      if (o.type === 'result') result = o;
    };
    const killer = setTimeout(() => { err += `\n${TRY_TIMEOUT_MS / 60000}분이 지나 멈춤`; killTree(child); }, TRY_TIMEOUT_MS);
    child.stdout.on('data', (d) => {
      const s = d.toString('utf-8');
      out += s;
      pending += s;
      const lines = pending.split(/\r?\n/);
      pending = lines.pop();
      lines.forEach(handle);
    });
    child.stderr.on('data', (d) => { err += d.toString('utf-8'); });
    child.on('error', (e) => { err += `\n실행 실패: ${e.message}`; });
    child.on('close', (code) => {
      clearTimeout(killer);
      if (pending) handle(pending);
      const sec = Math.round((Date.now() - started) / 1000);
      if (lockProblem) return resolve({ ok: false, problem: `[잠금] ${lockProblem}`, sec });
      if (!init) return resolve({ ok: false, problem: `클로드 시작 정보를 못 받음 (종료코드 ${code}) ${(err.trim() || out.trim()).slice(-400)}`, sec });
      if (!result || result.is_error || typeof result.result !== 'string') {
        return resolve({ ok: false, problem: `클로드 결과 없음/오류 (종료코드 ${code}) ${String((result && result.result) || err).slice(-300)}`, sec });
      }
      resolve({ ok: true, text: result.result, sec });
    });
    child.stdin.write(prompt, 'utf-8');
    child.stdin.end();
  });
}

// ── 숫자 다루기 ───────────────────────────────────
function numTokens(s) {
  // "3만 원" "46,200원" "16.5%" "2026년" → ["3","46200","16.5","2026"]
  return (String(s).match(/\d[\d,]*(?:\.\d+)?/g) || []).map((x) => x.replace(/,/g, ''));
}
function amount(s) {
  // 한국식 금액·수량을 숫자로: "30만 원"→300000, "1억 2천만"→120000000, "46,200원"→46200, "16.5%"→0.165
  const t = String(s).replace(/,/g, '').replace(/\s/g, '');
  let total = 0;
  let found = false;
  const re = /(\d+(?:\.\d+)?)(억|천만|백만|만|천)?/g;
  let m;
  const unit = { 억: 1e8, 천만: 1e7, 백만: 1e6, 만: 1e4, 천: 1e3 };
  while ((m = re.exec(t)) !== null) {
    found = true;
    total += parseFloat(m[1]) * (m[2] ? unit[m[2]] : 1);
  }
  if (found && /%|퍼센트/.test(t)) total /= 100;   // "10%"는 곱셈에서 0.1 (11/5 — 3000만 원 × 10%를 3억으로 계산한 검사기 실수 고침)
  return found ? total : NaN;
}
// 금액 표현을 값으로 모음 — "395만 2천 원"·"395.2만 원"·"3,952,000원"이 모두 3952000 (11/10 비광도기님: 표기만 다른 같은 금액을 "본문에 없음"으로 떨어뜨리던 것 고침)
const MONEY_RE = /\d[\d,]*(?:\.\d+)?\s*(?:억|천만|백만|만|천)(?:\s*\d[\d,]*(?:\.\d+)?\s*(?:천만|백만|만|천))*(?:\s*\d[\d,]*\s*원|\s*원)?|\d[\d,]*(?:\.\d+)?\s*원/g;
function moneyExprs(s) { return String(s).match(MONEY_RE) || []; }
function moneySet(s) { return new Set(moneyExprs(s).map((x) => Math.round(amount(x))).filter((v) => Number.isFinite(v) && v > 0)); }
function stripMd(s) {
  return String(s).replace(/\*\*|==|~~/g, '').replace(/^#+\s*/gm, '');
}

// ── 검사 ─────────────────────────────────────────
const LIMITS = {
  체크목록: (c) => arr(c.items, 2, 4, 'items') + strs(c.items, 20, 'items'),
  숫자강조: (c) => arr(c.cards, 1, 4, 'cards') + (Array.isArray(c.cards) ? c.cards.map((x, i) => need(x, ['label', 'value'], `cards[${i}]`) + len(x.label, 10, `cards[${i}].label`) + len(x.value, 11, `cards[${i}].value`)).join('') : ''),
  단계흐름: (c) => arr(c.steps, 3, 5, 'steps') + strs(c.steps, 12, 'steps'),
  나란히비교: (c) => arr(c.cols, 2, 3, 'cols') + (Array.isArray(c.cols) ? c.cols.map((x, i) => need(x, ['head', 'lines'], `cols[${i}]`) + len(x.head, 12, `cols[${i}].head`) + arr(x.lines, 1, 3, `cols[${i}].lines`) + strs(x.lines, 16, `cols[${i}].lines`)).join('') : ''),
  조건분기: (c) => need(c, ['root', 'left', 'right'], 'chart') + len(c.root, 12, 'root') + ['left', 'right'].map((k) => (c[k] ? need(c[k], ['if', 'then'], k) + len(c[k].if, 16, `${k}.if`) + len(c[k].then, 14, `${k}.then`) : '')).join(''),
  큰제목: (c) => arr(c.lines, 1, 2, 'lines') + strs(c.lines, 14, 'lines'),
  타임라인: (c) => arr(c.points, 2, 4, 'points') + (Array.isArray(c.points) ? c.points.map((x, i) => need(x, ['when', 'what'], `points[${i}]`) + len(x.when, 10, `points[${i}].when`) + len(x.what, 12, `points[${i}].what`)).join('') : ''),
  짝짓기목록: (c) => arr(c.rows, 2, 4, 'rows') + (Array.isArray(c.rows) ? c.rows.map((x, i) => (Array.isArray(x) && x.length === 2 ? len(x[0], 10, `rows[${i}][0]`) + len(x[1], 14, `rows[${i}][1]`) : `rows[${i}]는 [항목, 값] 두 칸이어야 함; `)).join('') : ''),
  항목나열: (c) => arr(c.chips, 3, 7, 'chips') + strs(c.chips, 10, 'chips') + (c.result ? len(c.result, 18, 'result') : ''),
  막대비교: (c) => arr(c.bars, 2, 5, 'bars') + (Array.isArray(c.bars) ? c.bars.map((x, i) => need(x, ['label', 'value'], `bars[${i}]`) + len(x.label, 8, `bars[${i}].label`) + (typeof x.value === 'number' ? '' : `bars[${i}].value는 따옴표 없는 숫자여야 함; `)).join('') : ''),
  포함제외: (c) => arr(c.in, 1, 4, 'in') + arr(c.out, 1, 4, 'out') + strs(c.in, 16, 'in') + strs(c.out, 16, 'out'),
  계산식: (c) => arr(c.terms, 2, 3, 'terms') + need(c, ['ops', 'result'], 'chart') + (c.result ? need(c.result, ['label', 'value'], 'result') : ''),
  누적막대: (c) => arr(c.parts, 2, 3, 'parts') + (Array.isArray(c.parts) ? c.parts.map((x, i) => need(x, ['label', 'value'], `parts[${i}]`) + (typeof x.value === 'number' ? '' : `parts[${i}].value는 숫자여야 함; `)).join('') : ''),
};
function arr(a, lo, hi, name) { return Array.isArray(a) && a.length >= lo && a.length <= hi ? '' : `${name}는 ${lo}~${hi}개여야 함; `; }
function strs(a, max, name) { return Array.isArray(a) ? a.map((s, i) => len(s, max, `${name}[${i}]`)).join('') : ''; }
function len(s, max, name) { return typeof s === 'string' && s.length > 0 && s.length <= max ? '' : `${name} "${String(s)}"는 1~${max}자여야 함; `; }
function need(o, keys, name) { return o && typeof o === 'object' ? keys.filter((k) => o[k] === undefined || o[k] === '').map((k) => `${name}.${k} 칸이 없음; `).join('') : `${name}이 비어 있음; `; }

function chartStrings(c) {
  const out = [];
  const walk = (v, k) => {
    if (k === 'type' || k === 'hl' || k === 'warn' || k === 'ops') return;
    if (typeof v === 'string' || typeof v === 'number') out.push(String(v));
    else if (Array.isArray(v)) v.forEach((x) => walk(x, ''));
    else if (v && typeof v === 'object') {
      // 값과 단위가 따로 있는 칸(막대 등 {"value":395.2,"unit":"만 원"})은 붙여서 하나로 — 금액 값 비교가 되게(11/10)
      const vu = (typeof v.value === 'string' || typeof v.value === 'number') && typeof v.unit === 'string';
      if (vu) out.push(`${v.value} ${v.unit}`);
      Object.entries(v).forEach(([kk, vv]) => { if (!(vu && (kk === 'value' || kk === 'unit'))) walk(vv, kk); });
    }
  };
  walk(c, '');
  return out;
}

function checkFormula(c) {
  // 계산식이 맞는지: terms[0] ops[0] terms[1] (ops[1] terms[2]) = result
  const vals = c.terms.map((x) => amount(x.value));
  const res = amount(c.result.value);
  if (vals.some((v) => Number.isNaN(v)) || Number.isNaN(res)) return '계산식 숫자를 읽을 수 없음';
  let acc = vals[0];
  for (let i = 1; i < vals.length; i += 1) {
    const op = String((c.ops || [])[i - 1] || '').trim();
    if (op === '+' ) acc += vals[i];
    else if (op === '−' || op === '-') acc -= vals[i];
    else if (op === '×' || op === 'x' || op === '*') acc *= vals[i];
    else return `계산 기호 "${op}"를 모름(+, −, × 중 하나)`;
  }
  return Math.abs(acc - res) <= Math.max(1, Math.abs(res) * 0.005) ? '' : `계산이 틀림: 결과는 ${acc}인데 ${res}로 적음`;
}

function validate(data, body, cat, bans, topics) {
  const errs = [];
  const bodyNums = new Set(numTokens(stripMd(body)));
  const bodyAmts = moneySet(stripMd(body));
  if (!data || !Array.isArray(data.scenes)) return ['scenes 목록이 없음'];
  const sc = data.scenes;
  if (sc.length < 9 || sc.length > 11) errs.push(`장면이 ${sc.length}개 — 9~11개여야 함`);
  if (!data.title || String(data.title).length > 40) errs.push('title은 1~40자여야 함');
  let total = 0;
  let couples = 0;
  let boards = 0;
  const seen = new Set();
  sc.forEach((s, i) => {
    const n = i + 1;
    const nar = String(s.narration || '');
    total += nar.length;
    if (nar.length < 40 || nar.length > 120) errs.push(`${n}장면 대사 ${nar.length}자 — 50~110자로`);
    if (/\*\*|==|##/.test(nar)) errs.push(`${n}장면 대사에 마크다운 기호가 있음`);
    nar.split(/(?<=[.?!])\s+/).forEach((sent) => sent.split(/(?<=,)\s+/).forEach((ph) => {
      if (ph.length > 32) errs.push(`${n}장면 구절 "${ph}" ${ph.length}자 — 쉼표로 끊어 32자 이하로`);
    }));
    const it = cat.byId[String(s.img || '').trim()];
    if (!it) errs.push(`${n}장면 img "${s.img}"는 창고에 없는 번호`);
    else {
      if (seen.has(it.id)) errs.push(`${n}장면 img ${it.id}를 이미 다른 장면에 씀 — 한 영상 안에서 한 번만`);
      seen.add(it.id);
      if (bans.hard.has(it.id)) errs.push(`${n}장면 img ${it.id}는 최근 글에 쓴 그림(금지)`);
      if (it.couple) couples += 1;
      if (it.board && !s.board) errs.push(`${n}장면 칠판 그림 ${it.id}에는 board("내림막대"/"오름막대")를 넣어야 함`);
      if (!it.board && s.board) errs.push(`${n}장면 board는 칠판 그림에만 — ${it.id}는 칠판 그림이 아님`);
    }
    if (!s.want || String(s.want).length > 40) errs.push(`${n}장면 want는 1~40자여야 함`);
    if (!MATCHES.includes(s.match)) errs.push(`${n}장면 match는 "딱맞음"·"비슷함"·"대체" 중 하나`);
    if (s.board) {
      boards += 1;
      if (!['내림막대', '오름막대'].includes(s.board)) errs.push(`${n}장면 board는 "내림막대" 또는 "오름막대"만`);
    }
    const c = s.chart || {};
    if (!LIMITS[c.type]) errs.push(`${n}장면 chart.type "${c.type}"은 13가지 틀에 없음`);
    else {
      const e = LIMITS[c.type](c);
      if (e) errs.push(`${n}장면 ${c.type}: ${e.trim()}`);
      if (c.title && String(c.title).length > 22) errs.push(`${n}장면 chart.title이 22자를 넘음`);
    }
    // 숫자 검사: 대사·도표의 숫자는 본문에 있어야 함 (계산식 결과는 계산이 맞으면 허용)
    let allowed = new Set();
    if (c.type === '계산식' && Array.isArray(c.terms) && c.result) {
      const fe = checkFormula(c);
      if (fe) errs.push(`${n}장면 ${fe}`);
      else numTokens(c.result.value).forEach((x) => allowed.add(x));
    }
    const strsAll = [nar, ...chartStrings(c)];
    strsAll.forEach((str) => {
      // 금액 표기가 본문과 달라도 값이 본문 금액과 같으면 그 숫자들은 인정
      const ok = new Set();
      moneyExprs(str).forEach((e) => { if (bodyAmts.has(Math.round(amount(e)))) numTokens(e).forEach((x) => ok.add(x)); });
      numTokens(str).forEach((x) => {
      if (!bodyNums.has(x) && !allowed.has(x) && !ok.has(x)) errs.push(`${n}장면 숫자 "${x}"가 본문에 없음 (${String(str).slice(0, 30)})`);
      });
    });
    if (/저도|제가 직접|해 봤는데|추천드립니다|가입하세요|매수|투자하세요|수익 보장/.test(nar)) errs.push(`${n}장면 대사에 금지 표현(경험담·권유)이 있음`);
  });
  if (total < 650 || total > 900) errs.push(`대사 합계 ${total}자 — 650~900자로`);
  if (couples < 2 || couples > 4) errs.push(`부부 그림 ${couples}장 — 2~4장으로`);
  if (topics && topics.length && !sc.some((s) => topics.some((x) => x.id === String(s.img || '').trim()))) {
    errs.push(`주제 그림 후보(${topics.map((x) => x.id).join(', ')}) 중 하나도 안 씀 — 1장면을 포함해 1~2장은 후보에서`);
  }
  if (boards > 2) errs.push(`칠판 그림 ${boards}장 — 2장까지`);
  if (sc[0] && (sc[0].chart || {}).type !== '큰제목') errs.push('1장면 chart는 큰제목이어야 함');
  const last = sc[sc.length - 1];
  if (last && !['체크목록', '큰제목'].includes((last.chart || {}).type)) errs.push('마지막 장면 chart는 체크목록 또는 큰제목이어야 함');
  return [...new Set(errs)];
}

function parseJson(text) {
  const a = text.indexOf('{');
  const b = text.lastIndexOf('}');
  if (a < 0 || b <= a) return null;
  try { return JSON.parse(text.slice(a, b + 1)); } catch (e) { return null; }
}

// ── 숏폼 장면표 (대본은 숏폼 것을 그대로, 그림은 긴 영상 장면 5개를 빌림) ──
function makeShort(longScenes, script, title) {
  const sents = String(script).trim().split(/(?<=[.?!])\s+/).filter(Boolean);
  const k = Math.min(5, sents.length);
  const groups = Array.from({ length: k }, () => []);
  sents.forEach((s, i) => groups[Math.min(k - 1, Math.floor((i * k) / sents.length))].push(s));
  const n = longScenes.length;
  const pick = [0, ...Array.from({ length: k - 1 }, (_, j) => Math.round(1 + ((j + 1) * (n - 2)) / k))].slice(0, k);
  return {
    title,
    scenes: groups.map((g, i) => ({
      no: i + 1,
      img: `scene_${String(pick[i] + 1).padStart(2, '0')}.png`,
      sec: Math.round((g.join(' ').length / 6.5) * 10) / 10,
      narration: g.join(' '),
      ...(longScenes[pick[i]].board ? { board: longScenes[pick[i]].board } : {}),
      chart: i === 0 ? { type: '큰제목', lines: [title.slice(0, 14), title.slice(14, 28)].filter(Boolean) } : longScenes[pick[i]].chart,
    })),
  };
}

// ── 실행 ─────────────────────────────────────────
// 쇼폼(short-make.js)이 검사·클로드 부르기를 같이 쓰도록 내보냄 (11/5). 직접 실행할 때만 아래 본흐름이 돎
module.exports = { runClaude, parseJson, loadCatalog, loadUsed, recentBans, catalogGuide, topicCandidates, TEMPLATE_GUIDE, LIMITS, chartStrings, checkFormula, numTokens, amount, moneySet, moneyExprs, MATCHES, REF_SOLO, REF_COUPLE, HERE };

if (require.main === module) (async () => {
  if (!ID || !/^\d{8}_r\d+$/.test(ID)) { log('사용법: node scene-make.js --id 20261103_r1 [--short-file 대본.txt --short-title 제목] [--dry]  또는  --job 작업.json'); process.exit(2); }
  let body = '';
  let title = '';
  if (JOB) {
    if (JOB.bad) { log(`[중단] 작업 파일을 못 읽음: ${JOB_FILE} (${JOB.bad})`); process.exit(2); }
    body = String(JOB.body || '').replace(/^\uFEFF/, '');
    title = String(JOB.blogTitle || '').trim();
    if (body.length < 300) { log(`[중단] 작업 파일의 본문이 비었거나 너무 짧음(${body.length}자): ${JOB_FILE}`); process.exit(2); }
  } else {
    const bodyPath = path.join(ASSETFLOW, `gen_${ID}.txt`);
    const titlePath = path.join(ASSETFLOW, 'temp-images', ID, 'title.txt');
    if (!fs.existsSync(bodyPath)) { log(`[중단] 본문이 없습니다: ${bodyPath}`); process.exit(2); }
    body = fs.readFileSync(bodyPath, 'utf8').replace(/^\uFEFF/, '');
    title = fs.existsSync(titlePath) ? fs.readFileSync(titlePath, 'utf8').replace(/^\uFEFF/, '').trim() : '';
  }
  log(`=== scene-make · ${ID} · ${new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })} KST · 모델 ${MODEL} ===`);
  log(`제목: ${title || '(title.txt 없음)'} · 본문 ${body.length}자`);
  const outDir = path.join(HERE, 'jobs', ID);
  fs.mkdirSync(outDir, { recursive: true });
  const cat = loadCatalog();
  if (!cat || cat.usable.length === 0) { log(`[중단] 창고 목록을 못 읽음: ${CATALOG_FILE}`); process.exit(2); }
  const missingFiles = cat.usable.filter((x) => !fs.existsSync(path.join(HERE, x.file)));
  if (missingFiles.length) {
    log(`[중단] 창고 그림 파일 ${missingFiles.length}개가 없음 (예: ${missingFiles.slice(0, 3).map((x) => `${x.id} ${x.file}`).join(' · ')})`);
    process.exit(2);
  }
  const used = loadUsed();
  const bans = recentBans(used, ID);
  const guide = catalogGuide(cat, bans);
  const topics = topicCandidates(cat, title, bans);
  log(`창고 그림 ${cat.usable.length}장 · 최근 금지 ${bans.hard.size}장 · 되도록 피함 ${bans.soft.size}장`);
  log(`주제 그림 후보: ${topics.length ? topics.map((x) => `${x.id} ${x.name}`).join(', ') : '없음'}`);
  if (DRY) {
    fs.writeFileSync(path.join(outDir, '_prompt.txt'), buildPrompt(title, body, '', guide, topics), 'utf8');
    log(`(--dry) 질문만 저장: ${path.join(outDir, '_prompt.txt')}`);
    return;
  }
  let note = '';
  let data = null;
  let errs = [];
  let tries = 0;
  for (tries = 1; tries <= MAX_TRIES; tries += 1) {
    log(`[${tries}/${MAX_TRIES}] 클로드에게 장면표 요청…`);
    // eslint-disable-next-line no-await-in-loop
    const r = await runClaude(buildPrompt(title, body, note, guide, topics));
    if (!r.ok) { log(`  ✘ ${r.problem}`); if (/\[잠금\]/.test(r.problem)) break; continue; }
    log(`  받음 ${r.sec}초 · ${r.text.length}자`);
    fs.writeFileSync(path.join(outDir, `_answer_${tries}.txt`), r.text, 'utf8');
    data = parseJson(r.text);
    if (!data) { errs = ['답이 JSON 모양이 아님']; note = 'JSON 하나로만 답해야 함 (앞뒤 설명 없이)'; log('  ✘ JSON을 못 읽음'); continue; }
    errs = validate(data, body, cat, bans, topics);
    if (errs.length === 0) { log('  ✓ 검사 통과'); break; }
    log(`  ✘ 검사 ${errs.length}건`);
    errs.slice(0, 30).forEach((e) => log(`    - ${e}`));
    note = errs.slice(0, 30).map((e) => `- ${e}`).join('\n');
  }
  if (!data || errs.length) {
    log(`=== 결과: 실패 — ${tries > MAX_TRIES ? MAX_TRIES : tries}번 시도 뒤에도 검사 ${errs.length}건 남음. 장면표를 만들지 않습니다 ===`);
    process.exit(1);
  }
  const scenes = data.scenes.map((s, i) => {
    const it = cat.byId[String(s.img).trim()];
    return {
      no: i + 1,
      sec: Math.round((String(s.narration).length / 6.5) * 10) / 10,
      img: it.id,
      img_name: it.name,
      img_file: it.file,
      want: s.want,
      match: s.match,
      couple: it.couple === true,
      ref: it.couple ? REF_COUPLE : REF_SOLO,
      scene: it.scene,
      camera: it.camera,
      ...(s.board ? { board: s.board } : {}),
      chart: s.chart,
      narration: s.narration,
    };
  });
  // 고른 그림을 이 글 폴더로 복사 (렌더러가 읽는 이름 scene_NN.png)
  // 같은 글의 예전 장면표가 있으면 지우지 않고 이름을 바꿔 남김 (11/4 — 덮어써서 옛 판을 잃은 뒤)
  const prev = path.join(outDir, 'scenes.json');
  if (fs.existsSync(prev)) fs.copyFileSync(prev, path.join(outDir, `scenes_이전_${RUN}.json`));
  const imgDir = path.join(outDir, 'img');
  fs.mkdirSync(imgDir, { recursive: true });
  fs.readdirSync(imgDir).filter((f) => /^scene_\d+\.png$/.test(f)).forEach((f) => fs.unlinkSync(path.join(imgDir, f)));
  scenes.forEach((s) => fs.copyFileSync(path.join(HERE, s.img_file), path.join(imgDir, `scene_${String(s.no).padStart(2, '0')}.png`)));
  const madeIso = new Date().toISOString();
  const out = { post: ID, title: data.title, blog_title: title, made: RUN, model: MODEL, tries, note: 'scene-make.js 자동 작성 (11/4 창고에서 고르기)', img_dir: 'img', scenes };
  fs.writeFileSync(path.join(outDir, 'scenes.json'), JSON.stringify(out, null, 2), 'utf8');
  const total = scenes.reduce((a, s) => a + s.narration.length, 0);
  log(`저장: ${path.join(outDir, 'scenes.json')} · 장면 ${scenes.length}개 · 대사 ${total}자(약 ${Math.round(total / 6.5)}초) · 틀 ${scenes.map((s) => s.chart.type).join('/')}`);
  log(`그림: ${scenes.map((s) => `${s.no}:${s.img}(${s.match})`).join(' ')} → ${imgDir}`);
  // 사용 기록 — 같은 글을 다시 만들면 그 글 줄만 바꿈
  const usedNext = used.filter((u) => u.post !== ID);
  usedNext.push({ post: ID, made: RUN, madeIso, ids: scenes.map((s) => s.img) });
  fs.writeFileSync(USED_FILE, JSON.stringify(usedNext, null, 1), 'utf8');
  // 부족 기록 — match가 "대체"인 장면 (같은 글 줄은 바꿈)
  const shortage = readJson(SHORTAGE_FILE, []);
  const shortNext = (Array.isArray(shortage) ? shortage : []).filter((x) => x.post !== ID);
  const kst = new Date(Date.now() + 9 * 3600000).toISOString().replace('T', ' ').slice(0, 16);
  scenes.filter((s) => s.match === '대체').forEach((s) => shortNext.push({ kst, post: ID, title: data.title, no: s.no, want: s.want, used: `${s.img} ${s.img_name}` }));
  fs.writeFileSync(SHORTAGE_FILE, JSON.stringify(shortNext, null, 1), 'utf8');
  const nAlt = scenes.filter((s) => s.match === '대체').length;
  log(`맞는 정도: 딱맞음 ${scenes.filter((s) => s.match === '딱맞음').length} · 비슷함 ${scenes.filter((s) => s.match === '비슷함').length} · 대체 ${nAlt}${nAlt ? ` → ${SHORTAGE_FILE}에 적음` : ''}`);
  if (SHORT_FILE) {
    const script = fs.readFileSync(path.resolve(SHORT_FILE), 'utf8').replace(/^\uFEFF/, '').trim();
    const short = makeShort(scenes, script, SHORT_TITLE || data.title);
    fs.writeFileSync(path.join(outDir, 'short.json'), JSON.stringify(short, null, 2), 'utf8');
    log(`저장: ${path.join(outDir, 'short.json')} · 장면 ${short.scenes.length}개`);
  }
  log('=== 결과: 성공 ===');
})();
