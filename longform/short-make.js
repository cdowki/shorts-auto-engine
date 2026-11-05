// short-make.js — 쇼츠 대본 → 새 틀 숏폼 장면표 + 그림 (쇼츠창 2026-11-05)
//
// 실행 (render_shorts.py가 부름 — 저장소 longform 폴더에서)
//   node short-make.js --out <폴더> --title "쇼츠 제목" --script-file 대본.txt [--tag 168]
// 결과
//   <폴더>/scenes.json — 렌더러(render_preview.py)가 읽는 장면표
//   <폴더>/img/scene_NN.png — 창고에서 고른 그림
// 끝 코드: 0 = 성공 · 1 = 검사를 끝내 통과 못 함 · 2 = 준비물 없음(이 경우 render_shorts.py가 예전 방식으로 만듦)
//
// 규칙 (11/5 비광도기님 승인 — 숏폼 자체 생성)
//   - 대사는 쇼츠 대본 그대로. 한 글자도 바꾸지 않고 5~7장면으로 나누기만 함(검사기가 이어 붙여 원문과 대조)
//   - 그림은 창고에서 고름. 한 영상 안 같은 그림 금지, 최근 긴 영상 3편에 쓴 그림 금지(기록은 읽기만)
//   - 위 카드 도표는 대본에 있는 숫자로만. 1장면은 큰제목(쇼츠 제목)
//   - 클로드 부르는 법은 긴 영상과 같음(구독·도구 0개·잠금 확인) — scene-make.js 것을 그대로 씀

'use strict';

const fs = require('fs');
const path = require('path');
const SM = require('./scene-make.js');

const argv = process.argv.slice(2);
const pickArg = (name, def) => {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : def;
};
const OUT = pickArg('--out', null);
const TITLE = String(pickArg('--title', '') || '').trim();
const SCRIPT_FILE = pickArg('--script-file', null);
const TAG = pickArg('--tag', 'short');
const MAX_TRIES = 3;
const HERE = SM.HERE;

function log(...a) { console.log('[short-make]', ...a); }
const norm = (s) => String(s).replace(/\s+/g, '');

function buildPrompt(title, script, retryNote, guide) {
  return `너는 5060 세대를 위한 생활 금융·제도 설명 세로 숏폼 영상의 장면표를 쓰는 작가야.
아래 [쇼츠 대본]을 장면으로 나누고, 장면마다 그림과 위 카드 도표를 붙여서 JSON 하나로만 답해줘. JSON 밖에는 아무 글자도 쓰지 마.

[가장 중요한 규칙 — 대사]
- 대본을 한 글자도 바꾸지 마. 고치거나 줄이거나 보태지 말고, 문장 경계(마침표·물음표 뒤)에서만 잘라 5~7장면으로 나눠.
- 장면 narration을 순서대로 이어 붙이면 [쇼츠 대본]과 띄어쓰기를 빼고 정확히 같아야 해.
- 장면 하나에 1~3문장. 장면 길이는 비슷하게.

[도표 규칙 — chart 칸]
- 1장면 chart는 "큰제목" — 쇼츠 제목을 2줄로(줄마다 12자 이하, 필요하면 줄여서 핵심만).
- 2장면부터는 그 장면 대사 내용에 가장 맞는 도표 틀을 아래 13가지에서 고름. 같은 틀을 연달아 쓰지 마.
- 도표에 쓰는 숫자는 반드시 [쇼츠 대본]에 있는 숫자만. 대본에 없는 숫자·날짜·기관명은 쓰지 마. 숫자가 없는 장면은 체크목록·단계흐름·포함제외·조건분기·항목나열·큰제목처럼 글로 된 틀을 써.
- 마지막 장면 chart는 "체크목록" 또는 "큰제목".
- 마크다운 기호(**, ==, ##)는 쓰지 마.

[그림 규칙 — img·want·match 칸]
- 그림은 아래 [그림 창고]에서 고름. 장면 대사에 가장 맞는 번호 하나를 img에 씀(예: "E06").
- want: 이 장면에 원래 가장 어울리는 그림을 한 줄로(30자 이하). match: "딱맞음" / "비슷함" / "대체" 중 정직하게.
- 한 영상 안에서 같은 번호를 두 번 쓰지 마. "[금지:최근 사용]" 번호는 쓰지 마. "[되도록 피함]" 번호는 다른 마땅한 그림이 없을 때만.
- 1장면 그림은 주제가 바로 보이는 그림(병원·연금·집·보험 등 주제 묶음)으로.
- "칠판" 그림은 1장까지이고, 칠판 그림을 쓴 장면에만 "board":"내림막대" 또는 "오름막대"를 넣음.

${SM.TEMPLATE_GUIDE}

${guide}

[답 모양]
{"scenes":[{"no":1,"img":"E16","want":"…","match":"딱맞음","chart":{"type":"큰제목","lines":["…","…"]},"narration":"(대본 앞부분 그대로)"}, …]}
${retryNote ? `\n[지난 답에서 고칠 것 — 반드시 모두 고쳐서 처음부터 다시 써줘]\n${retryNote}\n` : ''}
[쇼츠 제목]
${title}

[쇼츠 대본]
${script}
`;
}

function validate(data, script, cat, bans) {
  const errs = [];
  if (!data || !Array.isArray(data.scenes)) return ['scenes 목록이 없음'];
  const sc = data.scenes;
  if (sc.length < 5 || sc.length > 7) errs.push(`장면이 ${sc.length}개 — 5~7개여야 함`);
  const joined = sc.map((s) => String(s.narration || '')).join('');
  if (norm(joined) !== norm(script)) {
    const a = norm(joined);
    const b = norm(script);
    let k = 0;
    while (k < a.length && k < b.length && a[k] === b[k]) k += 1;
    errs.push(`장면 대사를 이으면 대본과 다름 — ${k}번째 글자부터 다름(대본: "${b.slice(Math.max(0, k - 8), k + 12)}" / 답: "${a.slice(Math.max(0, k - 8), k + 12)}"). 대본을 한 글자도 바꾸지 말고 나누기만`);
  }
  const scriptNums = new Set(SM.numTokens(script));
  const seen = new Set();
  let boards = 0;
  let prevType = '';
  sc.forEach((s, i) => {
    const n = i + 1;
    const nar = String(s.narration || '');
    if (nar.length < 15) errs.push(`${n}장면 대사가 너무 짧음(${nar.length}자) — 장면을 합쳐서`);
    const it = cat.byId[String(s.img || '').trim()];
    if (!it) errs.push(`${n}장면 img "${s.img}"는 창고에 없는 번호`);
    else {
      if (seen.has(it.id)) errs.push(`${n}장면 img ${it.id}를 이미 다른 장면에 씀`);
      seen.add(it.id);
      if (bans.hard.has(it.id)) errs.push(`${n}장면 img ${it.id}는 최근 사용 그림(금지)`);
      if (it.board && !s.board) errs.push(`${n}장면 칠판 그림 ${it.id}에는 board("내림막대"/"오름막대")를 넣어야 함`);
      if (!it.board && s.board) errs.push(`${n}장면 board는 칠판 그림에만`);
    }
    if (s.board) {
      boards += 1;
      if (!['내림막대', '오름막대'].includes(s.board)) errs.push(`${n}장면 board는 "내림막대" 또는 "오름막대"만`);
    }
    if (!s.want || String(s.want).length > 40) errs.push(`${n}장면 want는 1~40자여야 함`);
    if (!SM.MATCHES.includes(s.match)) errs.push(`${n}장면 match는 "딱맞음"·"비슷함"·"대체" 중 하나`);
    const c = s.chart || {};
    if (!SM.LIMITS[c.type]) errs.push(`${n}장면 chart.type "${c.type}"은 13가지 틀에 없음`);
    else {
      const e = SM.LIMITS[c.type](c);
      if (e) errs.push(`${n}장면 ${c.type}: ${e.trim()}`);
      if (c.title && String(c.title).length > 22) errs.push(`${n}장면 chart.title이 22자를 넘음`);
      if (i > 0 && c.type === prevType) errs.push(`${n}장면 도표 틀 "${c.type}"이 앞 장면과 같음 — 다른 틀로`);
      prevType = c.type;
    }
    const allowed = new Set();
    if (c.type === '계산식' && Array.isArray(c.terms) && c.result) {
      const fe = SM.checkFormula(c);
      if (fe) errs.push(`${n}장면 ${fe}`);
      else SM.numTokens(c.result.value).forEach((x) => allowed.add(x));
    }
    if (i > 0) {
      SM.chartStrings(c).forEach((str) => SM.numTokens(str).forEach((x) => {
        if (!scriptNums.has(x) && !allowed.has(x)) errs.push(`${n}장면 도표 숫자 "${x}"가 대본에 없음 (${String(str).slice(0, 30)})`);
      }));
    }
  });
  if (boards > 1) errs.push(`칠판 그림 ${boards}장 — 1장까지`);
  if (sc[0] && (sc[0].chart || {}).type !== '큰제목') errs.push('1장면 chart는 큰제목이어야 함');
  const last = sc[sc.length - 1];
  if (last && !['체크목록', '큰제목'].includes((last.chart || {}).type)) errs.push('마지막 장면 chart는 체크목록 또는 큰제목이어야 함');
  return [...new Set(errs)];
}

(async () => {
  if (!OUT || !SCRIPT_FILE || !TITLE) { log('사용법: node short-make.js --out 폴더 --title 제목 --script-file 대본.txt'); process.exit(2); }
  const script = fs.readFileSync(SCRIPT_FILE, 'utf8').replace(/^﻿/, '').trim();
  if (script.length < 100) { log(`대본이 너무 짧음(${script.length}자)`); process.exit(2); }
  const cat = SM.loadCatalog();
  if (!cat || !cat.usable.length) { log('창고 목록을 못 읽음'); process.exit(2); }
  const missing = cat.usable.filter((x) => !fs.existsSync(path.join(HERE, x.file)));
  if (missing.length) { log(`창고 그림 파일 ${missing.length}개 없음`); process.exit(2); }
  const bans = SM.recentBans(SM.loadUsed(), `short_${TAG}`);   // 최근 긴 영상 3편 그림은 금지(읽기만)
  const guide = SM.catalogGuide(cat, bans);
  fs.mkdirSync(OUT, { recursive: true });
  log(`제목: ${TITLE} · 대본 ${script.length}자 · 창고 ${cat.usable.length}장 · 금지 ${bans.hard.size}장`);

  let note = '';
  let data = null;
  let errs = [];
  let tries;
  for (tries = 1; tries <= MAX_TRIES; tries += 1) {
    log(`[${tries}/${MAX_TRIES}] 클로드에게 숏폼 장면표 요청…`);
    // eslint-disable-next-line no-await-in-loop
    const r = await SM.runClaude(buildPrompt(TITLE, script, note, guide));
    if (!r.ok) { log(`  ✘ ${r.problem}`); if (/\[잠금\]/.test(r.problem)) break; continue; }
    log(`  받음 ${r.sec}초 · ${r.text.length}자`);
    data = SM.parseJson(r.text);
    if (!data) { errs = ['답이 JSON 모양이 아님']; note = 'JSON 하나로만 답해야 함'; log('  ✘ JSON을 못 읽음'); continue; }
    errs = validate(data, script, cat, bans);
    if (!errs.length) { log('  ✓ 검사 통과'); break; }
    log(`  ✘ 검사 ${errs.length}건`);
    errs.slice(0, 20).forEach((e) => log(`    - ${e}`));
    note = errs.slice(0, 20).map((e) => `- ${e}`).join('\n');
  }
  if (!data || errs.length) { log(`=== 결과: 실패 — 검사 ${errs.length}건 남음 ===`); process.exit(1); }

  const imgDir = path.join(OUT, 'img');
  fs.mkdirSync(imgDir, { recursive: true });
  const scenes = data.scenes.map((s, i) => {
    const it = cat.byId[String(s.img).trim()];
    fs.copyFileSync(path.join(HERE, it.file), path.join(imgDir, `scene_${String(i + 1).padStart(2, '0')}.png`));
    return {
      no: i + 1,
      sec: Math.round((String(s.narration).length / 6.5) * 10) / 10,
      img: it.id,
      img_name: it.name,
      want: s.want,
      match: s.match,
      couple: it.couple === true,
      ...(s.board ? { board: s.board } : {}),
      chart: s.chart,
      narration: String(s.narration).trim(),
    };
  });
  const out = { post: `short_${TAG}`, title: TITLE, made: new Date().toISOString(), tries, note: 'short-make.js 숏폼 자체 생성(11/5)', img_dir: 'img', scenes };
  fs.writeFileSync(path.join(OUT, 'scenes.json'), JSON.stringify(out, null, 2), 'utf8');
  log(`저장: 장면 ${scenes.length}개 · 그림 ${scenes.map((s) => `${s.img}(${s.match})`).join(' ')} · 틀 ${scenes.map((s) => s.chart.type).join('/')}`);
  log('=== 결과: 성공 ===');
})();
