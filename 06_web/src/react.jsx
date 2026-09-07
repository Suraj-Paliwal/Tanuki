/**
 * React Three Fiber wrapper.
 *
 *   import { Tanuki } from 'tanuki-lipsync/react';
 *
 *   const ref = useRef();
 *   <Canvas camera={{ position: [0, 0.5, 1.9], fov: 40 }}>
 *     <Tanuki ref={ref} url="/models/tanuki_visemes.glb" />
 *   </Canvas>
 *   ...
 *   await ref.current.speak({ audio: '/tts/line.mp3', track });
 */
import React, { forwardRef, useImperativeHandle, useMemo, useRef, useEffect } from 'react';
import { useFrame, useLoader } from '@react-three/fiber';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { TanukiLipSync } from './tanuki-lipsync.js';

export const Tanuki = forwardRef(function Tanuki(
  { url, idleBlink = true, attack, release, onReady, ...props },
  ref
) {
  const gltf = useLoader(GLTFLoader, url);
  const group = useRef();

  // useLoader caches by URL, so two <Tanuki> with the same url would share one
  // scene graph and fight over the same morph influences. Clone per instance.
  const scene = useMemo(() => gltf.scene.clone(true), [gltf]);

  const rig = useMemo(
    () => new TanukiLipSync(scene, { idleBlink, attack, release }),
    [scene, idleBlink, attack, release]
  );

  useEffect(() => { onReady?.(rig); }, [rig, onReady]);
  useFrame((_, dt) => rig.update(dt));

  useImperativeHandle(ref, () => ({
    speak: (o) => rig.speak(o),
    listen: (s, c) => rig.listen(s, c),
    stop: () => rig.stop(),
    setViseme: (n, v, i) => rig.setViseme(n, v, i),
    setVisemes: (o, i) => rig.setVisemes(o, i),
    get rig() { return rig; },
    get object() { return scene; },
  }), [rig, scene]);

  return <group ref={group} {...props}><primitive object={scene} /></group>;
});

export default Tanuki;
