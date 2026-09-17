import * as THREE from 'three';
import { GLTFLoader }        from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment }   from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer }    from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass }        from 'three/addons/postprocessing/RenderPass.js';
import { ShaderPass }        from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass }        from 'three/addons/postprocessing/OutputPass.js';
import { TanukiLipSync }               from './tanuki-lipsync.js';
import { BodyMotion }                  from './body.js';
import { applyTextureQuality, CASShader } from './quality.js';

const MODEL = './model/tanuki.gltf';

/* Load the existing Tanuki morph-target rig. */

const canvas   = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;

const scene  = new THREE.Scene();
scene.background = new THREE.Color(0x1a1d23);
scene.environment = new THREE.PMREMGenerator(renderer)
  .fromScene(new RoomEnvironment(), 0.04).texture;
const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 100);

scene.add(new THREE.HemisphereLight(0xffffff, 0x33384a, 0.9));
for (const [x, y, z, i] of [[-1.6, 2.2, 2.6, 2.2], [2.2, 0.6, 1.6, 0.7], [0.6, 1.8, -2.4, 1.1]]) {
  const l = new THREE.DirectionalLight(0xffffff, i); l.position.set(x, y, z); scene.add(l);
}

// RenderPass -> OutputPass -> sharpen. OutputPass is not optional: the composer
// renders to a linear target, so without it tone mapping and the sRGB
// conversion stop happening and everything comes out washed and orange.
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new OutputPass());
const cas = new ShaderPass(CASShader);
cas.uniforms.sharpness.value = 0.25;
composer.addPass(cas);

function resize() {
  const r = canvas.parentElement.getBoundingClientRect();
  const w = Math.max(1, r.width | 0), h = Math.max(1, r.height | 0);
  renderer.setSize(w, h, false); composer.setSize(w, h);
  const dpr = renderer.getPixelRatio();
  cas.uniforms.resolution.value.set(w * dpr, h * dpr);
  camera.aspect = w / h; camera.updateProjectionMatrix();
}
addEventListener('resize', resize);

const status = document.getElementById('status');
let tanuki = null, rig = null, body = null;
try {
  tanuki = await TanukiLipSync.load(MODEL, new GLTFLoader());
  rig = new THREE.Group(); rig.add(tanuki.object); scene.add(rig);
  body = new BodyMotion(rig);
  applyTextureQuality(tanuki.object, renderer);   // anisotropy; off by default in three.js

  // Frame the head and shoulders. glTF is Y-up while the model was authored
  // Z-up, so the face sits about 70% of the way up the body - aiming at the
  // bounding-box centre points the camera at the belly.
  const box  = new THREE.Box3().setFromObject(tanuki.object);
  const size = box.getSize(new THREE.Vector3());
  const mid  = box.getCenter(new THREE.Vector3());
  const y    = box.min.y + size.y * 0.68;
  camera.position.set(mid.x - 0.02, y, mid.z + size.y * 1.55);
  camera.lookAt(mid.x - 0.02, y - 0.06, mid.z);
  resize();
  status.textContent = 'ready';
} catch (e) {
  status.textContent = 'model failed to load';
  console.error(e);
}

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = clock.getDelta();
  if (tanuki) { tanuki.update(dt); body.update(dt, tanuki); }
  composer.render();
});


const $ = id => document.getElementById(id);
const audio = new Audio();
audio.preload = 'auto';
let connected = false, busy = false, last = null, generation = 0, controller;
function buttons() {
  $('speak').disabled = busy || !connected || !tanuki;
  $('replay').disabled = busy || !last || !tanuki;
  $('stop').disabled = !busy;
  $('voice').disabled = busy || !connected;
  $('speed').disabled = busy;
}
async function connect() {
  $('reconnect').disabled = true;
  $('connection').textContent = 'Connecting to AivisSpeech…';
  try {
    const result = await fetch('/api/status');
    const data = await result.json();
    connected = data.ready;
    const previous = $('voice').value;
    $('voice').replaceChildren(...data.voices.map(v => new Option(`${v.name} · ${v.style}`, v.id)));
    if (data.voices.some(v => v.id === previous)) $('voice').value = previous;
    else if (data.default_voice) $('voice').value = data.default_voice;
    $('connection').textContent = connected ? '● AivisSpeech connected · Local voice' : data.message;
  } catch (e) {
    connected = false;
    $('connection').textContent = 'Cannot reach the local server. Run start.ps1, then reconnect.';
  }
  $('connection').classList.toggle('error', !connected);
  $('reconnect').disabled = false;
  buttons();
}
$('reconnect').onclick = connect;
$('text').oninput = () => $('count').textContent = `${$('text').value.length} / 160`;
$('text').oninput();
for (const button of document.querySelectorAll('[data-text]')) button.onclick = () => {
  $('text').value = button.dataset.text; $('text').oninput();
};
$('speed').oninput = () => $('speed-value').textContent = `${Number($('speed').value).toFixed(2)}×`;
$('offset').oninput = () => {
  $('offset-value').textContent = `${$('offset').value} ms`;
  if (tanuki) tanuki.offset = Number($('offset').value) / 1000;
};
for (const name of ['A','I','U','E','O']) {
  const meter = document.createElement('div'); meter.className = 'meter';
  meter.innerHTML = `${name}<i><b></b></i>`; $('meters').append(meter);
}
const meters = [...document.querySelectorAll('.meter b')];
function updateMeters() {
  ['A','I','U','E','O'].forEach((v, i) => meters[i].style.width = `${100 * (tanuki?.current[v] || 0)}%`);
  requestAnimationFrame(updateMeters);
}
updateMeters();
async function play(result, token) {
  if (token !== generation) return;
  audio.src = result.audio;
  status.textContent = 'Speaking · AivisSpeech';
  await tanuki.speak({audio, track:result.track});
}
async function run(replay = false) {
  if (busy || !tanuki) return;
  const token = ++generation;
  busy = true; buttons();
  // Resume the audio context inside the user's click, before network work.
  tanuki.measureLatency().catch(() => {});
  try {
    if (!replay) {
      status.textContent = 'Generating your voice…';
      $('details').textContent = 'AivisSpeech is preparing the line. The first request may load the voice model.';
      controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 240000);
      let response;
      try {
        response = await fetch('/api/say', {method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({text:$('text').value, voice:$('voice').value, speed:Number($('speed').value)}),
          signal:controller.signal});
      } finally { clearTimeout(timer); }
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Speech generation failed.');
      if (token !== generation) return;
      last = result;
      $('details').textContent = `${result.duration.toFixed(2)} s · Audio-aligned lip timing (estimated)\nReading: ${result.kana}`;
      $('downloads').hidden = false;
      $('audio-link').href = result.audio;
      $('track-link').href = result.audio.replace('.wav', '.json');
    }
    await play(last, token);
    if (token === generation) status.textContent = 'Ready · replay or try another line';
  } catch (e) {
    if (token === generation) {
      status.textContent = 'Could not play this line';
      $('details').textContent = e.name === 'AbortError' ? 'Speech took too long. Check the AivisSpeech engine, then retry.' : e.message;
    }
  } finally {
    if (token === generation) { busy = false; buttons(); }
  }
}
$('form').onsubmit = e => {e.preventDefault(); run();};
$('replay').onclick = () => run(true);
$('stop').onclick = () => {
  generation++; controller?.abort(); audio.pause(); tanuki?.stop();
  busy = false; buttons(); status.textContent = 'Stopped · ready';
};
window.tanukiReady = !!tanuki;
connect();
setInterval(() => { if (!connected && !busy && !$('reconnect').disabled) connect(); }, 10000);
