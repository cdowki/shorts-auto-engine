// run_daily.js — 긴 영상(유튜브 1~3분) 서버 묶음 실행 (쇼츠창 2026-11-04)
//
// 깃허브 Actions(.github/workflows/longform.yml)가 매일 한 번 부름. PC는 쓰지 않음.
//   1) 쇼츠 GAS에 "긴 영상으로 만들 글 목록"을 본문과 함께 받음 (longform_jobs, with_body — 54초쯤 걸려 5분까지 기다림)
//   2) 시작일(START_ID, 기본 20261105) 이후 글 · 아직 안 만든 글 · 본문이 온 글만 (오래된 것부터, 한 번에 MAX_POSTS편까지)
//   3) 글마다: scene-make.js(창고에서 그림 고르기, 클로드 구독) → tts-make.js(목소리) → render_preview.py(영상)
//   4) 영상은 이 저장소 릴리스(longform-<글번호>)에 올려 주소를 만듦
//   4-b) 유튜브 업로드 (11/5 추가) — 스위치 YT_UPLOAD: '1' 켬 · 'dry' 시험(열쇠만 확인, 올리지 않음) · 그 밖 끔(그림자 운행)
//        제목 = 같은 글의 쇼츠 제목(시트 D열, 9/14 규칙을 거친 것) · 바로 공개 · AI 표시 켬 (11/5 비광도기님 결정)
//        막는 조건: 장면표가 첫 시도에 통과 못 함 · 대체 그림 2장 이상 · 쇼츠 제목 없음 · 이미 올린 글 · 한 번에 YT_MAX편 넘음
//   5) 결과를 GAS longform_result로 보내 "[긴 영상] …" 메일 한 통
//   6) 기록: done.json(만든 글) · 창고_사용기록.json · 창고_부족기록.json · jobs/<글>/scenes.json — 저장소 저장은 워크플로가 함
//
// 실행: node longform/run_daily.js [--only 20261105_r1] [--max 4] [--no-mail]
// 부르는 곳(11/5~): 쇼츠 GAS가 매일 10시대 repository_dispatch "longform_daily" · 예비로 깃허브 예약 11:37 KST(할 일 없으면 메일 없음)
// 비밀값(환경 변수): CALLBACK_URL · CALLBACK_SECRET · TTS_API_KEY · CLAUDE_CODE_OAUTH_TOKEN · GH_TOKEN · GH_REPOSITORY
//   + 유튜브(yt_upload.py): GOOGLE_OAUTH_CLIENT_ID · GOOGLE_OAUTH_CLIENT_SECRET · YOUTUBE_REFRESH_TOKEN
//   값은 화면·기록·메일 어디에도 찍지 않음
// 끝 코드: 0 = 정상(만든 글 0편 포함) · 1 = 글 일부/전부 실패 · 2 = 목록을 못 받음

'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const HERE = __dirname;
const argv = process.argv.slice(2);
const pickArg = (name, def) => {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] !== undefined && !argv[i + 1].startsWith('--') ? argv[i + 1] : def;
};
const ONLY = pickArg('--only', process.env.ONLY_POST || '') || '';
const MAX_POSTS = Number(pickArg('--max', process.env.MAX_POSTS || '4')) || 4;
const NO_MAIL = argv.includes('--no-mail');
const RUN_EVENT = process.env.RUN_EVENT || '';                 // schedule = 예비 예약 실행 (11/5 — 본 실행은 GAS가 부름)
const START_ID = process.env.START_ID || '20261105';     // 이 날짜(글 번호 앞 8자리)부터 만듦 — 그 앞 밀린 글은 건너뜀 (11/4 비광도기님 확인)
const VOICE = 'ko-KR-Chirp3-HD-Algieba';
const RATE = '0.95';
const DONE_FILE = path.join(HERE, 'done.json');
const MAX_FAILS = 2;                                       // 같은 글이 이만큼 실패하면 더 시도하지 않음
const GAS_TIMEOUT_MS = 5 * 60 * 1000;
const YT_MODE = String(process.env.YT_UPLOAD || '0').trim();   // '1' 켬 · 'dry' 시험 · 그 밖 끔
const YT_ON = YT_MODE === '1' || YT_MODE === 'dry';
const YT_MAX = 3;                                          // 한 번 실행에 유튜브로 보내는 편수 상한(하루 사용 한도 때문)
let ytSent = 0;

function kstNow() {
  return new Date(Date.now() + 9 * 3600000).toISOString().replace('T', ' ').slice(0, 16);
}
const RUN = kstNow().replace(/[-: ]/g, '').slice(0, 12);    // 예: 202611051617
function log(...a) { console.log(`[${kstNow().slice(11)}]`, ...a); }
function readJson(file, def) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8').replace(/^﻿/, '')); } catch (e) { return def; }
}

// ── GAS ─────────────────────────────────────────
async function gas(payload, timeoutMs) {
  const url = process.env.CALLBACK_URL;
  const secret = process.env.CALLBACK_SECRET;
  if (!url || !secret) throw new Error('CALLBACK_URL / CALLBACK_SECRET 비밀값이 없습니다');
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ secret, ...payload }),
    redirect: 'follow',
    signal: AbortSignal.timeout(timeoutMs),
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch (e) { throw new Error(`GAS 응답을 읽지 못함 [${res.status}] ${text.slice(0, 160)}`); }
  if (!data.ok) throw new Error(`GAS가 거절함: ${data.error || text.slice(0, 160)}`);
  return data;
}

// ── 깃허브 릴리스 (영상 공개 주소) ──────────────────────
async function gh(method, url, body, headers) {
  const token = process.env.GH_TOKEN;
  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(headers || {}),
    },
    body,
    signal: AbortSignal.timeout(5 * 60 * 1000),
  });
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch (e) { /* 무시 */ }
  return { status: res.status, data, text };
}
// 릴리스 올리기 — 네트워크 오류(11/6 EPIPE로 실행 전체가 멈춤)가 나도 실행을 멈추지 않고 3번까지 다시 시도 (11/6)
async function uploadRelease(file, postId, title) {
  let last = '';
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      // eslint-disable-next-line no-await-in-loop
      const r = await uploadReleaseOnce(file, postId, title, attempt);
      if (r.url) return attempt > 1 ? { url: r.url, note: `릴리스 ${attempt}번째에 올라감 (앞 실패: ${last})` } : r;
      last = r.note;
    } catch (e) {
      last = `네트워크 오류 ${(e.cause && e.cause.code) || e.message}`;
    }
    if (attempt < 3) {
      log(`  릴리스 올리기 다시 시도 (${attempt}/3 실패: ${String(last).slice(0, 100)})`);
      // eslint-disable-next-line no-await-in-loop
      await new Promise((res) => setTimeout(res, 15000));
    }
  }
  return { url: '', note: `영상 올리기 3번 실패 — ${last}` };
}
async function uploadReleaseOnce(file, postId, title, attempt) {
  const repo = process.env.GH_REPOSITORY;
  if (!process.env.GH_TOKEN || !repo) return { url: '', note: 'GH_TOKEN/GH_REPOSITORY 없음 — 릴리스 건너뜀' };
  const api = `${process.env.GH_API || 'https://api.github.com'}/repos/${repo}`;   // GH_API는 시험용(가짜 서버)
  const tag = `longform-${postId}`;
  let rel = await gh('GET', `${api}/releases/tags/${tag}`);
  if (rel.status === 404) {
    rel = await gh('POST', `${api}/releases`, JSON.stringify({
      tag_name: tag, name: `긴 영상 ${postId} — ${String(title).slice(0, 60)}`,
      body: '긴 영상(유튜브 1~3분) 자동 제작 결과 — 그림자 운행 확인용', draft: false, prerelease: false,
    }), { 'Content-Type': 'application/json' });
  }
  if (rel.status >= 300 || !rel.data || !rel.data.upload_url) return { url: '', note: `릴리스 만들기 실패 [${rel.status}] ${rel.text.slice(0, 120)}` };
  const name = `${postId}_${RUN}${attempt > 1 ? `_${attempt}` : ''}.mp4`;   // 다시 시도 때는 이름을 바꿔 '이미 있음' 거절을 피함
  const up = await gh('POST', `${rel.data.upload_url.split('{')[0]}?name=${encodeURIComponent(name)}`, fs.readFileSync(file), { 'Content-Type': 'video/mp4' });
  if (up.status >= 300 || !up.data) return { url: '', note: `영상 올리기 실패 [${up.status}] ${up.text.slice(0, 120)}` };
  return { url: up.data.browser_download_url || '', note: '' };
}

// ── 한 단계 실행 ─────────────────────────────────────
function step(label, cmd, args, opts) {
  const started = Date.now();
  log(`▶ ${label}`);
  const r = spawnSync(cmd, args, { cwd: HERE, stdio: 'inherit', timeout: (opts && opts.timeoutMs) || 20 * 60 * 1000, env: { ...process.env, ...((opts && opts.env) || {}) } });
  const sec = Math.round((Date.now() - started) / 1000);
  const ok = r.status === 0;
  log(`${ok ? '✓' : '✘'} ${label} — ${sec}초${ok ? '' : ` (끝 코드 ${r.status}${r.error ? ` · ${r.error.message}` : ''}${r.signal ? ` · ${r.signal}` : ''})`}`);
  return { ok, sec, code: r.status };
}
function lastLogLines(prefix, n) {
  // scene_*.txt / tts_*.txt 중 가장 최근 것의 끝 몇 줄 (실패 이유를 메일에 넣으려고)
  const dir = path.join(HERE, 'logs');
  if (!fs.existsSync(dir)) return '';
  const f = fs.readdirSync(dir).filter((x) => x.startsWith(prefix)).sort().pop();
  if (!f) return '';
  return fs.readFileSync(path.join(dir, f), 'utf8').split(/\r?\n/).filter(Boolean).slice(-n).join('\n');
}
function duration(file) {
  const r = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file], { encoding: 'utf8' });
  return Math.round(Number(String(r.stdout).trim()) || 0);
}

// ── 유튜브 ──────────────────────────────────────
function ytBlock(out, job, prev) {
  // 올리지 않을 이유를 돌려줌. 빈 글자면 올림
  if (!YT_ON) return '꺼짐(그림자 운행)';
  if (prev && prev.youtube) return `이미 올린 글 — ${prev.youtube}`;
  if (out.tries !== 1) return `장면표가 ${out.tries}번째에 통과 — 올리지 않음`;
  if ((out.match && out.match.대체) >= 2) return `대체 그림 ${out.match.대체}장 — 올리지 않음`;
  if (!String(job.shortsTitle || '').trim()) return '쇼츠 제목(시트 D열)이 없음 — 올리지 않음';
  if (ytSent >= YT_MAX) return `한 번에 ${YT_MAX}편까지 — 올리지 않음(다음 실행에서도 다시 올리지는 않음, 손 실행 필요)`;
  return '';
}
function ytUpload(mp4, job) {
  const id = job.postId;
  const title = String(job.shortsTitle).trim();
  const descFile = path.join(HERE, 'jobs', id, 'yt_desc.txt');
  fs.writeFileSync(descFile, `${title}\n\n블로그 글을 바탕으로 정리한 설명 영상입니다.\n영상 속 그림과 목소리는 AI로 만들었습니다.\n`, 'utf8');
  const args = ['yt_upload.py', '--file', mp4, '--title', title, '--desc-file', descFile];
  if (YT_MODE === 'dry') args.push('--dry-run');
  log(`▶ ${id} 유튜브${YT_MODE === 'dry' ? ' 시험(올리지 않음)' : ' 올리기'}`);
  ytSent += 1;
  const r = spawnSync('python3', args, { cwd: HERE, encoding: 'utf8', timeout: 20 * 60 * 1000 });
  const outText = String(r.stdout || '');
  process.stdout.write(outText);
  if (r.stderr) process.stdout.write(String(r.stderr).split('\n').slice(-5).join('\n') + '\n');
  let res = null;
  try { res = JSON.parse(outText.trim().split('\n').pop()); } catch (e) { /* 아래에서 처리 */ }
  if (!res) return { url: '', note: `유튜브 결과를 못 읽음 (끝 코드 ${r.status})` };
  if (!res.ok) {
    if (/quota/i.test(res.error || '')) ytSent = YT_MAX;   // 하루 한도에 걸리면 이번 실행은 더 보내지 않음
    return { url: '', note: `유튜브 실패: ${res.error}` };
  }
  if (res.dry) return { url: '', note: '유튜브 시험 통과 — 열쇠 맞음, 올리지 않음' };
  return { url: res.url, note: '' };
}

// ── 글 한 편 ──────────────────────────────────────
async function makeOne(job, prev) {
  const id = job.postId;
  const out = { postId: id, row: job.row, blogTitle: job.blogTitle, blogLink: job.blogLink || '', made: RUN, status: '실패' };
  const jobDir = path.join(HERE, 'jobs', id);
  fs.mkdirSync(jobDir, { recursive: true });
  const jobFile = path.join(jobDir, 'job.json');   // 본문이 들어 있어 저장소에는 저장하지 않음(워크플로가 고른 파일만 저장)
  fs.writeFileSync(jobFile, JSON.stringify({ postId: id, blogTitle: job.blogTitle, body: job.body }, null, 1), 'utf8');

  const s1 = step(`${id} 장면표(창고에서 그림 고르기)`, 'node', ['scene-make.js', '--job', jobFile], { timeoutMs: 30 * 60 * 1000 });
  if (!s1.ok) { out.reason = `장면표 실패\n${lastLogLines('scene_', 8)}`; return out; }
  const sc = readJson(path.join(jobDir, 'scenes.json'), null);
  if (!sc || !Array.isArray(sc.scenes)) { out.reason = '장면표 파일을 못 읽음'; return out; }
  out.title = sc.title;
  out.tries = sc.tries;
  out.match = { 딱맞음: 0, 비슷함: 0, 대체: 0 };
  sc.scenes.forEach((s) => { out.match[s.match] = (out.match[s.match] || 0) + 1; });
  out.alt = sc.scenes.filter((s) => s.match === '대체').map((s) => `${s.no}번 장면: 원한 그림 "${s.want}" → 쓴 그림 ${s.img} ${s.img_name}`);
  out.imgs = sc.scenes.map((s) => s.img);

  const s2 = step(`${id} 목소리`, 'node', ['tts-make.js', '--scenes', path.join('jobs', id, 'scenes.json'), '--voice', VOICE, '--rate', RATE], { timeoutMs: 15 * 60 * 1000 });
  if (!s2.ok) { out.reason = `목소리 실패\n${lastLogLines('tts_', 6)}`; return out; }
  const ttsDir = path.join(HERE, `tts_${id}_${VOICE}_r${RATE}_p`);

  fs.mkdirSync(path.join(HERE, 'out'), { recursive: true });
  const mp4 = path.join(HERE, 'out', `${id}.mp4`);
  const s3 = step(`${id} 영상 만들기`, 'python3', ['render_preview.py', path.join('jobs', id, 'scenes.json'), path.join('jobs', id, 'img'), mp4], { timeoutMs: 40 * 60 * 1000, env: { TTS: ttsDir, WIDE: '1' } });   // 긴 영상은 가로(16:9) — 세로 3분 이하는 쇼츠로 분류돼 시청 시간에 안 들어감 (11/6)
  if (!s3.ok || !fs.existsSync(mp4)) { out.reason = '영상 만들기 실패 (깃허브 실행 기록을 보십시오)'; return out; }
  out.sec = duration(mp4);
  out.mb = Math.round((fs.statSync(mp4).size / 1048576) * 10) / 10;
  out.minutes = Math.round((s1.sec + s2.sec + s3.sec) / 6) / 10;

  const rel = await uploadRelease(mp4, id, out.title);
  out.video = rel.url;
  if (rel.note) out.note = rel.note;
  out.status = rel.url ? '만듦' : '만듦(주소 없음)';

  out.youtube = (prev && prev.youtube) || '';
  const block = ytBlock(out, job, prev);
  if (block) {
    out.ytNote = block;
  } else {
    const yt = ytUpload(mp4, job);
    out.youtube = yt.url;
    out.ytNote = yt.note;
    if (yt.url) out.ytNew = true;
  }
  return out;
}

function mailText(results, skipped, info) {
  const L = [];
  const mode = YT_MODE === '1' ? '유튜브 자동 업로드 켬' : YT_MODE === 'dry' ? '유튜브 시험(열쇠만 확인, 올리지 않음)' : '그림자 운행(유튜브에 올리지 않음)';
  L.push(`긴 영상 서버 실행 ${kstNow()} KST — ${mode}`);
  L.push(`목록 ${info.total}편 · 시작일(${START_ID}) 앞 ${info.old}편 건너뜀 · 이미 만든 글 ${info.done}편 · 본문 안 온 글 ${info.noBody}편`);
  L.push('');
  if (!results.length) L.push('오늘 새로 만든 글은 없습니다.');
  results.forEach((r, i) => {
    L.push(`■ ${i + 1}. ${r.postId} · ${r.status}`);
    L.push(`  블로그 제목: ${r.blogTitle}`);
    if (r.title) L.push(`  영상 제목: ${r.title}`);
    if (r.video) L.push(`  영상: ${r.video}`);
    if (r.youtube) L.push(`  유튜브: ${r.youtube}`);
    if (r.ytNote && YT_ON) L.push(`  유튜브 참고: ${r.ytNote}`);
    if (r.sec) L.push(`  길이 ${Math.floor(r.sec / 60)}분 ${r.sec % 60}초 · ${r.mb}MB · 만드는 데 ${r.minutes}분 · 장면표 ${r.tries}번째에 통과`);
    if (r.match) L.push(`  그림 맞는 정도: 딱맞음 ${r.match.딱맞음} · 비슷함 ${r.match.비슷함} · 대체 ${r.match.대체}`);
    (r.alt || []).forEach((a) => L.push(`  ※ 대체 — ${a}`));
    if (r.reason) L.push(`  실패 이유: ${r.reason}`);
    if (r.note) L.push(`  참고: ${r.note}`);
    L.push('');
  });
  if (skipped.length) {
    L.push('다음에 다시 시도:');
    skipped.forEach((s) => L.push(`  ${s}`));
  }
  return L.join('\n');
}

(async () => {
  log(`=== run_daily · ${kstNow()} KST · 시작일 ${START_ID} · 한 번에 ${MAX_POSTS}편까지${ONLY ? ` · 이 글만 ${ONLY}` : ''} ===`);
  let jobs;
  try {
    const started = Date.now();
    const data = await gas({ action: 'longform_jobs', with_body: true }, GAS_TIMEOUT_MS);
    jobs = Array.isArray(data.jobs) ? data.jobs : [];
    log(`GAS 목록 ${jobs.length}편 · ${Math.round((Date.now() - started) / 1000)}초`);
  } catch (e) {
    log(`=== 결과: 실패 — 글 목록을 못 받음: ${e.message} ===`);
    process.exit(2);
  }
  const done = readJson(DONE_FILE, {});
  const info = { total: jobs.length, old: 0, done: 0, noBody: 0 };
  const todo = [];
  const skipped = [];
  jobs.slice().sort((a, b) => String(a.postId).localeCompare(String(b.postId))).forEach((j) => {
    const id = String(j.postId || '');
    if (!/^\d{8}_r\d+$/.test(id)) return;
    if (ONLY && id !== ONLY) return;
    if (!ONLY && id.slice(0, 8) < START_ID) { info.old += 1; return; }
    const d = done[id];
    if (d && (d.status !== '실패' || (d.fails || 0) >= MAX_FAILS) && !ONLY) { info.done += 1; return; }
    if (typeof j.body !== 'string' || j.body.length < 300) { info.noBody += 1; skipped.push(`${id} — 드라이브 본문이 아직 없음`); return; }
    todo.push(j);
  });
  const now = todo.slice(0, MAX_POSTS);
  todo.slice(MAX_POSTS).forEach((j) => skipped.push(`${j.postId} — 한 번에 ${MAX_POSTS}편까지라 다음 실행으로`));
  log(`만들 글 ${now.length}편: ${now.map((j) => j.postId).join(', ') || '없음'}`);

  const results = [];
  for (const j of now) {
    // eslint-disable-next-line no-await-in-loop
    const prev = done[j.postId] || {};
    let r;
    try {
      r = await makeOne(j, prev);
    } catch (e) {
      // 예상 못 한 오류가 나도 다음 글·결과 메일·기록은 계속 (11/6)
      log(`✘ ${j.postId} 예상 못 한 오류: ${e.message}`);
      r = { postId: j.postId, row: j.row, blogTitle: j.blogTitle, blogLink: j.blogLink || '', made: RUN, status: '실패', reason: `예상 못 한 오류: ${e.message}${e.cause && e.cause.code ? ` (${e.cause.code})` : ''}` };
    }
    results.push(r);
    done[j.postId] = { ...r, fails: r.status === '실패' ? (prev.fails || 0) + 1 : 0 };
    delete done[j.postId].reason;
    delete done[j.postId].ytNew;
    if (prev.youtube && !done[j.postId].youtube) done[j.postId].youtube = prev.youtube;   // 다시 만들다 실패해도 올린 기록은 지키기
    if (r.status === '실패') done[j.postId].lastReason = String(r.reason || '').split('\n')[0];
    fs.writeFileSync(DONE_FILE, JSON.stringify(done, null, 1), 'utf8');
    log(`— ${j.postId}: ${r.status}${r.video ? ` · ${r.video}` : ''}`);
  }

  const nOk = results.filter((r) => r.status !== '실패').length;
  const nFail = results.length - nOk;
  const nAlt = results.reduce((a, r) => a + ((r.match && r.match.대체) || 0), 0);
  const nYt = results.filter((r) => r.ytNew).length;
  const subject = `결과 ${kstNow().slice(0, 10)} — 만듦 ${nOk}편 · 실패 ${nFail}편${nAlt ? ` · 대체 그림 ${nAlt}장` : ''}${YT_MODE === '1' ? ` · 유튜브 ${nYt}편` : ''}`;
  const text = mailText(results, skipped, info);
  console.log(`\n----- 메일 -----\n${subject}\n${text}\n----------------`);
  const quietBackup = RUN_EVENT === 'schedule' && results.length === 0;   // 예비 예약이 할 일 없이 돌면 메일을 보내지 않음(본 실행이 이미 보냄)
  if (quietBackup) log('예비 예약 실행 — 새로 만든 글이 없어 메일은 보내지 않음');
  if (!NO_MAIL && !quietBackup) {
    try {
      const m = await gas({ action: 'longform_result', subject, text }, 60 * 1000);
      log(`결과 메일 보냄 (${JSON.stringify(m.mail === undefined ? '' : m.mail).slice(0, 60)})`);
    } catch (e) {
      log(`결과 메일 실패: ${e.message}`);
    }
  }
  log(`=== 결과: ${nFail ? '일부 실패' : '성공'} — 만듦 ${nOk} · 실패 ${nFail} ===`);
  process.exit(nFail ? 1 : 0);
})();
