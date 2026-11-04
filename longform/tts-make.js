// tts-make.js — 긴 영상·숏폼 내레이션 음성 만들기 (구글 클라우드 Text-to-Speech, 쇼츠창 2026-11-02)
//
// 키: 환경 변수 TTS_API_KEY(서버), 없으면 이 폴더의 .env 에서 TTS_API_KEY 한 줄만 읽습니다. 키 값은 화면·기록 어디에도 찍지 않습니다.
//     (구글 클라우드 newsscript 프로젝트의 '음성-긴영상' 키 — Cloud Text-to-Speech API 하나만 쓰도록 제한됨)
// 요금: Chirp 3 HD·Neural2 는 매달 100만 글자까지 무료. 실행할 때마다 보낸 글자 수를 기록에 남깁니다.
//
// 실행 (C:\shorts-clip\longform 에서)
//   node tts-make.js --sample
//       한국어 목소리 목록을 받아 남녀 고급 목소리 몇 개로 같은 문장을 읽혀 samples_<시각>\ 에 mp3로 저장
//   node tts-make.js --scenes scenes_20261030_r1.json --voice ko-KR-Chirp3-HD-Charon [--rate 1.0] [--no-split] [--only 6]
//       장면표의 장면마다 문장을 쉼표(,)에서 나눠 구절마다 mp3를 만들어 tts_<글번호>_<목소리>_r<빠르기>_p\ 에 저장 (+ _목록.json)
//       구절 사이 쉼(0.35초)은 영상 만들 때 넣습니다. --no-split 을 붙이면 예전처럼 문장 통째로 (폴더 끝 _p 없음)
//       (11/3 비광도기 결정: 쉼표에서 끊어 읽기 — D 방식)
//
// 기록: logs\tts_<시각>.txt (보낸 글자 수 포함)

'use strict';

const fs = require('fs');
const path = require('path');
const https = require('https');

const HERE = __dirname;
const LOG_DIR = path.join(HERE, 'logs');
const MAX_CHARS_PER_RUN = 20000;   // 한 번 실행에 보내는 글자 상한 (무료 100만 자의 2%)

const argv = process.argv.slice(2);
const pickArg = (name, def) => {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] !== undefined ? argv[i + 1] : def;
};
const DO_SAMPLE = argv.includes('--sample');
const SCENES_ARG = pickArg('--scenes', null);
const VOICE_ARG = pickArg('--voice', null);
const RATE = parseFloat(pickArg('--rate', '1.0')) || 1.0;
const SPLIT = !argv.includes('--no-split');
const ONLY = String(pickArg('--only', '')).split(',').map((x) => parseInt(x, 10)).filter((x) => x > 0);   // 예: --only 6  (그 장면만 다시 만듦, 나머지 파일·목록은 그대로)

function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}
if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
const RUN = stamp();
const RUN_LOG = path.join(LOG_DIR, `tts_${RUN}.txt`);
function log(...a) {
  const line = a.join(' ');
  console.log(line);
  try { fs.appendFileSync(RUN_LOG, `${line}\r\n`, 'utf8'); } catch (e) { /* 무시 */ }
}

function readKey() {
  // 서버(깃허브)에서는 비밀 보관함 TTS_API_KEY 가 환경 변수로 들어옴 (11/4). PC는 예전처럼 .env
  if (process.env.TTS_API_KEY && process.env.TTS_API_KEY.trim()) return process.env.TTS_API_KEY.trim();
  const f = path.join(HERE, '.env');
  if (!fs.existsSync(f)) return '';
  const txt = fs.readFileSync(f, 'utf8').replace(/^\uFEFF/, '');
  const m = txt.match(/^\s*TTS_API_KEY\s*=\s*(\S+)\s*$/m);
  return m ? m[1].replace(/^["']|["']$/g, '') : '';
}
const KEY = readKey();

// 키는 주소에 넣지 않고 머리글(X-Goog-Api-Key)로 보냅니다 — 오류가 나도 주소에 키가 찍히지 않게
function call(method, apiPath, body) {
  return new Promise((resolve) => {
    const data = body ? Buffer.from(JSON.stringify(body), 'utf8') : null;
    const req = https.request({
      host: 'texttospeech.googleapis.com', path: apiPath, method,
      headers: Object.assign({ 'X-Goog-Api-Key': KEY }, data ? { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': data.length } : {}),
      timeout: 60000,
    }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        const raw = Buffer.concat(chunks).toString('utf8');
        let json = null;
        try { json = JSON.parse(raw); } catch (e) { /* 아래 */ }
        resolve({ status: res.statusCode, json, raw: raw.slice(0, 400) });
      });
    });
    req.on('timeout', () => { req.destroy(); resolve({ status: 0, json: null, raw: '시간 초과(60초)' }); });
    req.on('error', (e) => resolve({ status: 0, json: null, raw: String(e.message || e) }));
    if (data) req.write(data);
    req.end();
  });
}
function errText(r) {
  const m = r.json && r.json.error ? `${r.json.error.status || ''} ${r.json.error.message || ''}` : r.raw;
  return `HTTP ${r.status} ${String(m).replace(/\s+/g, ' ').slice(0, 300)}`;
}

let sentChars = 0;
async function synth(text, voice, outFile) {
  if (sentChars + text.length > MAX_CHARS_PER_RUN) throw new Error(`한 번 실행 글자 상한(${MAX_CHARS_PER_RUN}자)을 넘어 멈춥니다`);
  const body = {
    input: { text },
    voice: { languageCode: 'ko-KR', name: voice },
    audioConfig: { audioEncoding: 'MP3', speakingRate: RATE, sampleRateHertz: 24000 },
  };
  const r = await call('POST', '/v1/text:synthesize', body);
  sentChars += text.length;
  if (r.status !== 200 || !r.json || !r.json.audioContent) throw new Error(errText(r));
  fs.writeFileSync(outFile, Buffer.from(r.json.audioContent, 'base64'));
  return fs.statSync(outFile).size;
}

// 렌더러와 같은 기준으로 문장을 나눕니다 (마침표·물음표·느낌표 뒤)
function sentences(txt) {
  return String(txt || '').trim().split(/(?<=[.?!])\s+/).filter(Boolean);
}

// 큰 숫자를 한글 읽기로 바꿈 — 음성에만 씀(자막·_목록.json의 글은 숫자 그대로)
// 11/3 비광도기님 지적: 구글 음성이 "144,372원"을 "백사십사 삼백칠십이원"으로 읽음
// 바꾸는 것: 쉼표가 든 숫자(144,372 · 1,500)와 쉼표 없는 1만 이상 정수. 30% · 2025년 · 3만 원 같은 짧은 숫자는 그대로
const DIGIT = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구'];
function sinoUnder10000(n) {
  let out = '';
  [[1000, '천'], [100, '백'], [10, '십'], [1, '']].forEach(([u, name]) => {
    const d = Math.floor(n / u) % 10;
    if (d === 0) return;
    out += (d === 1 && name ? '' : DIGIT[d]) + name;
  });
  return out;
}
function sino(n) {
  if (n === 0) return '영';
  const parts = [];
  [[1e12, '조'], [1e8, '억'], [1e4, '만'], [1, '']].forEach(([u, name]) => {
    const g = Math.floor(n / u) % 10000;
    if (g === 0) return;
    parts.push((g === 1 && name === '만' ? '' : sinoUnder10000(g)) + name);
  });
  return parts.join(' ');
}
function speakable(text) {
  return String(text).replace(/\d{1,3}(?:,\d{3})+(?!\.\d)|\d{5,}(?![.,]\d)/g, (m) => {
    const n = parseInt(m.replace(/,/g, ''), 10);
    return Number.isSafeInteger(n) ? sino(n) : m;
  });
}

// 쉼표 뒤에서 구절로 나눔 (쉼표는 구절 끝에 그대로 둠)
function phrases(sent) {
  return SPLIT ? sent.split(/(?<=,)\s+/).filter(Boolean) : [sent];
}

async function sampleMode() {
  log('=== tts-make — 목소리 듣기 견본 ===');
  const r = await call('GET', '/v1/voices?languageCode=ko-KR', null);
  if (r.status !== 200 || !r.json) { log(`[중단] 목소리 목록을 못 받았습니다: ${errText(r)}`); process.exit(1); }
  const voices = (r.json.voices || []).filter((v) => (v.languageCodes || []).includes('ko-KR'));
  const list = voices.map((v) => `${v.name}\t${v.ssmlGender}`).sort();
  fs.writeFileSync(path.join(LOG_DIR, `voices_ko_${RUN}.txt`), list.join('\r\n'), 'utf8');
  log(`한국어 목소리 ${voices.length}개 (목록: logs\\voices_ko_${RUN}.txt)`);
  const chirpM = voices.filter((v) => /Chirp3-HD/.test(v.name) && v.ssmlGender === 'MALE').map((v) => v.name).sort().slice(0, 4);
  const chirpF = voices.filter((v) => /Chirp3-HD/.test(v.name) && v.ssmlGender === 'FEMALE').map((v) => v.name).sort().slice(0, 4);
  const neural = voices.filter((v) => /Neural2/.test(v.name)).map((v) => v.name).sort();
  const pick = [...chirpM, ...chirpF, ...neural];
  if (pick.length === 0) { log('[중단] 고급(Chirp3-HD)·중급(Neural2) 한국어 목소리를 못 찾았습니다'); process.exit(1); }
  const text = '퇴직하면서 회사가 IRP 계좌를 알려 달라고 하셨나요? 결론부터 말씀드리면, 퇴직금을 받은 날부터 60일 안에 IRP에 넣으면 퇴직소득세를 미룰 수 있습니다.';
  const dir = path.join(HERE, `samples_${RUN}`);
  fs.mkdirSync(dir, { recursive: true });
  let ok = 0;
  for (let i = 0; i < pick.length; i += 1) {
    const v = pick[i];
    const g = (voices.find((x) => x.name === v) || {}).ssmlGender || '';
    const name = `${String(i + 1).padStart(2, '0')}_${g === 'MALE' ? '남' : g === 'FEMALE' ? '여' : '?'}_${v}.mp3`;
    try {
      // eslint-disable-next-line no-await-in-loop
      const size = await synth(text, v, path.join(dir, name));
      ok += 1;
      log(`  ${name} … 완료 ${Math.round(size / 1024)}KB`);
    } catch (e) {
      log(`  ${name} … 실패 — ${e.message}`);
    }
  }
  log(`=== 결과: ${ok}/${pick.length}개 · 보낸 글자 ${sentChars}자 · 폴더 ${dir} ===`);
}

async function scenesMode() {
  if (!VOICE_ARG) { log('[중단] --voice 목소리이름 을 붙여 주십시오 (예: ko-KR-Chirp3-HD-Charon)'); process.exit(2); }
  const file = path.isAbsolute(SCENES_ARG) ? SCENES_ARG : path.join(HERE, SCENES_ARG);
  if (!fs.existsSync(file)) { log(`[중단] 장면표가 없습니다: ${file}`); process.exit(2); }
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  // 폴더 이름표: 예전 장면표(scenes_20261030_r1.json)는 파일 이름에서, 자동 장면표(jobs\<번호>\scenes.json · short.json)는 글 번호에서
  const base = path.basename(file, '.json');
  const postId = data.post || path.basename(path.dirname(file));
  const tag = base === 'scenes' ? postId : base === 'short' ? `short_${postId}` : base.replace(/^scenes_/, '');
  const dir = path.join(HERE, `tts_${tag}_${VOICE_ARG}_r${RATE}${SPLIT ? '_p' : ''}`);
  fs.mkdirSync(dir, { recursive: true });
  log(`=== tts-make — 장면 음성 · ${path.basename(file)} · ${VOICE_ARG} · 빠르기 ${RATE} · ${SPLIT ? '쉼표에서 나눔' : '문장 통째'} ===`);
  const manifest = { scenes: path.basename(file), voice: VOICE_ARG, rate: RATE, split: SPLIT, made: RUN, items: [] };
  let fail = 0;
  for (let si = 0; si < data.scenes.length; si += 1) {
    if (ONLY.length && !ONLY.includes(si + 1)) continue;
    const sc = data.scenes[si];
    const ss = sentences(sc.narration);
    let stop = false;
    for (let k = 0; k < ss.length && !stop; k += 1) {
      const ps = phrases(ss[k]);
      for (let q = 0; q < ps.length; q += 1) {
        const name = `scene_${String(si + 1).padStart(2, '0')}_${String(k + 1).padStart(2, '0')}${SPLIT ? `_${String(q + 1).padStart(2, '0')}` : ''}.mp3`;
        try {
          // eslint-disable-next-line no-await-in-loop
          const said = speakable(ps[q]);
          const size = await synth(said, VOICE_ARG, path.join(dir, name));
          manifest.items.push({ scene: si + 1, n: k + 1, p: q + 1, last: q === ps.length - 1, file: name, text: ps[q], ...(said !== ps[q] ? { said } : {}) });
          log(`  ${name} … ${Math.round(size / 1024)}KB · ${ps[q].length}자${said !== ps[q] ? ` · 읽기: ${said}` : ''}`);
        } catch (e) {
          fail += 1;
          log(`  ${name} … 실패 — ${e.message}`);
          if (/상한/.test(e.message)) { stop = true; break; }
        }
      }
    }
  }
  if (ONLY.length) {
    // 고른 장면만 새로 만들었으면, 나머지 장면 목록은 예전 _목록.json 것을 그대로 이어 붙임
    const old = path.join(dir, '_목록.json');
    if (fs.existsSync(old)) {
      const prev = JSON.parse(fs.readFileSync(old, 'utf8'));
      const keep = (prev.items || []).filter((it) => !ONLY.includes(it.scene));
      manifest.items = [...keep, ...manifest.items].sort((x, y) => x.scene - y.scene || x.n - y.n || (x.p || 1) - (y.p || 1));
      log(`  --only ${ONLY.join(',')}: 나머지 장면 ${keep.length}개 파일은 그대로 둠`);
    }
  }
  fs.writeFileSync(path.join(dir, '_목록.json'), JSON.stringify(manifest, null, 2), 'utf8');
  log(`=== 결과: 파일 ${manifest.items.length}개 · 실패 ${fail} · 보낸 글자 ${sentChars}자 · 폴더 ${dir} ===`);
  process.exit(fail ? 2 : 0);
}

(async () => {
  if (!KEY) { log('[중단] TTS_API_KEY 가 없습니다 (PC는 .env 줄, 서버는 비밀 보관함)'); process.exit(2); }
  log(`시작: ${new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })} KST (키 길이 ${KEY.length}자 — 값은 찍지 않음)`);
  if (DO_SAMPLE) await sampleMode();
  else if (SCENES_ARG) await scenesMode();
  else log('사용법: node tts-make.js --sample  또는  node tts-make.js --scenes 장면표.json --voice 목소리이름 [--rate 1.0] [--no-split]');
})();
