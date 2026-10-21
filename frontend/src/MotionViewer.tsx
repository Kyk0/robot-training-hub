import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { Pause, Play, RotateCcw } from "lucide-react";
import { api } from "./api";

export default function MotionViewer({ motionId }: { motionId: string }) {
  const mount = useRef<HTMLDivElement>(null),
    playback = useRef({ playing: false, frame: 0, speed: 1 });
  const [motion, setMotion] = useState<any>(),
    [frame, setFrame] = useState(0),
    [playing, setPlaying] = useState(false),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let dead = false,
      animation = 0,
      renderer: THREE.WebGLRenderer | undefined,
      observer: ResizeObserver | undefined;
    const geometries: THREE.BufferGeometry[] = [],
      materials: THREE.Material[] = [];
    let controls: OrbitControls | undefined;
    setLoading(true);
    setError("");
    setPlaying(false);
    playback.current = { playing: false, frame: 0, speed: 1 };
    (async () => {
      try {
        const [model, data] = await Promise.all([
          api("/robot/model"),
          api("/motions/" + motionId + "/preview"),
        ]);
        if (dead) return;
        setMotion(data);
        const container = mount.current!;
        renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
        renderer.setClearColor(0xf1f4ed);
        container.appendChild(renderer.domElement);
        const scene = new THREE.Scene(),
          camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
        camera.up.set(0, 0, 1);
        camera.position.set(1.8, -2.2, 1.2);
        scene.add(new THREE.HemisphereLight(0xffffff, 0x839279, 2.5));
        const light = new THREE.DirectionalLight(0xffffff, 3);
        light.position.set(2, -3, 5);
        scene.add(light);
        const grid = new THREE.GridHelper(8, 40, 0xb9c7af, 0xd8e0d1);
        grid.rotation.x = Math.PI / 2;
        scene.add(grid);
        controls = new OrbitControls(camera, renderer.domElement);
        controls.target.set(0, 0, 0.45);
        controls.enableDamping = true;
        controls.update();
        const loader = new STLLoader(),
          cache = new Map<string, Promise<THREE.BufferGeometry>>(),
          joints = new Map<
            string,
            {
              group: THREE.Group;
              base: THREE.Quaternion;
              axis: THREE.Vector3;
              pivot: THREE.Vector3;
              position: THREE.Vector3;
            }
          >();
        const quat = (v: number[]) =>
          new THREE.Quaternion(v[1], v[2], v[3], v[0]);
        const build = async (node: any): Promise<THREE.Group> => {
          const group = new THREE.Group();
          group.name = node.name;
          group.position.fromArray(node.pos);
          group.quaternion.copy(quat(node.quat));
          if (node.joint)
            joints.set(node.joint.name, {
              group,
              base: group.quaternion.clone(),
              axis: new THREE.Vector3().fromArray(node.joint.axis).normalize(),
              pivot: new THREE.Vector3().fromArray(node.joint.pos),
              position: group.position.clone(),
            });
          await Promise.all(
            node.geoms.map(async (g: any) => {
              const spec = model.meshes[g.mesh];
              if (!cache.has(spec.file))
                cache.set(
                  spec.file,
                  fetch("/api/robot/meshes/" + encodeURIComponent(spec.file))
                    .then((r) => {
                      if (!r.ok) throw Error("Robot mesh could not be loaded");
                      return r.arrayBuffer();
                    })
                    .then((raw) => {
                      const geo = loader.parse(raw);
                      geometries.push(geo);
                      return geo;
                    }),
                );
              const geometry = await cache.get(spec.file)!;
              const material = new THREE.MeshStandardMaterial({
                color: new THREE.Color(
                  ...(g.color.slice(0, 3) as [number, number, number]),
                ),
                roughness: 0.6,
                metalness: 0.15,
              });
              materials.push(material);
              const mesh = new THREE.Mesh(geometry, material);
              mesh.position.fromArray(g.pos);
              mesh.quaternion.copy(quat(g.quat));
              mesh.scale.fromArray(spec.scale);
              group.add(mesh);
            }),
          );
          for (const child of node.children) group.add(await build(child));
          return group;
        };
        const robot = await build(model.body);
        if (dead) return;
        scene.add(robot);
        setLoading(false);
        const origin = new THREE.Vector3(data.data[0][0], data.data[0][1], 0);
        let last = performance.now(),
          lastState = 0;
        const resize = () => {
          if (!renderer) return;
          const w = container.clientWidth,
            h = container.clientHeight;
          renderer.setSize(w, h);
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
        };
        observer = new ResizeObserver(resize);
        observer.observe(container);
        resize();
        const tick = (now: number) => {
          if (dead) return;
          const delta = Math.min((now - last) / 1000, 0.1);
          last = now;
          const state = playback.current;
          if (state.playing)
            state.frame =
              (state.frame + delta * data.fps * state.speed) % data.frames;
          const index = Math.floor(state.frame),
            row = data.data[index];
          robot.position.set(row[0] - origin.x, row[1] - origin.y, row[2]);
          robot.quaternion.set(row[3], row[4], row[5], row[6]).normalize();
          data.joint_names.forEach((name: string, i: number) => {
            const joint = joints.get(name);
            if (!joint) return;
            const rotation = new THREE.Quaternion().setFromAxisAngle(
              joint.axis,
              row[7 + i],
            );
            joint.group.quaternion.copy(joint.base).multiply(rotation);
            joint.group.position
              .copy(joint.position)
              .add(
                joint.pivot
                  .clone()
                  .sub(joint.pivot.clone().applyQuaternion(rotation))
                  .applyQuaternion(joint.base),
              );
          });
          controls!.update();
          renderer!.render(scene, camera);
          if (now - lastState > 100) {
            setFrame(index);
            lastState = now;
          }
          animation = requestAnimationFrame(tick);
        };
        animation = requestAnimationFrame(tick);
      } catch (e) {
        if (!dead) {
          setError((e as Error).message);
          setLoading(false);
        }
      }
    })();
    return () => {
      dead = true;
      cancelAnimationFrame(animation);
      observer?.disconnect();
      controls?.dispose();
      geometries.forEach((g) => g.dispose());
      materials.forEach((m) => m.dispose());
      renderer?.dispose();
      renderer?.domElement.remove();
    };
  }, [motionId]);
  return (
    <section className="panel motion-preview">
      <div className="motion-canvas" ref={mount} />
      {loading && <div className="viewer-message">Loading Booster K1…</div>}
      {error && <div className="error">{error}</div>}
      <div className="motion-controls">
        <button
          aria-label={playing ? "Pause motion" : "Play motion"}
          disabled={!motion || loading}
          onClick={() => {
            playback.current.playing = !playing;
            setPlaying(!playing);
          }}
        >
          {playing ? <Pause size={18} /> : <Play size={18} />}
        </button>
        <button
          aria-label="Restart motion"
          onClick={() => {
            playback.current.frame = 0;
            setFrame(0);
          }}
        >
          <RotateCcw size={17} />
        </button>
        <input
          aria-label="Motion timeline"
          type="range"
          min={0}
          max={(motion?.frames || 1) - 1}
          value={frame}
          onChange={(e) => {
            playback.current.frame = Number(e.target.value);
            setFrame(Number(e.target.value));
          }}
        />
        <span>
          {(frame / (motion?.fps || 50)).toFixed(1)} /{" "}
          {(motion?.duration || 0).toFixed(1)} s
        </span>
        <select
          aria-label="Playback speed"
          onChange={(e) => (playback.current.speed = Number(e.target.value))}
          defaultValue="1"
        >
          <option value="0.5">0.5×</option>
          <option value="1">1×</option>
          <option value="2">2×</option>
        </select>
      </div>
      <p className="viewer-note">
        Reference motion from the CSV. Drag to rotate; scroll to zoom. This
        preview is not a trained policy.
      </p>
    </section>
  );
}
