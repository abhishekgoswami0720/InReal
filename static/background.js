// Slow floating shapes behind the page (three.js). Shared by the landing page and the dashboard;
// does nothing when three.js did not load or there is no #topo-radar-canvas.
function initGlassTranslucentBackground() {
  const canvas = document.getElementById('topo-radar-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 1000);
  camera.position.set(0, 0, 40);

  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  const group = new THREE.Group();
  scene.add(group);

  const materials = [
    new THREE.MeshBasicMaterial({ color: 0xF59E0B, transparent: true, opacity: 0.12 }),
    new THREE.MeshBasicMaterial({ color: 0x3B82F6, transparent: true, opacity: 0.10 }),
    new THREE.MeshBasicMaterial({ color: 0x10B981, transparent: true, opacity: 0.10 }),
  ];

  const meshes = [];

  for (let i = 0; i < 16; i++) {
    const geo = (i % 2 === 0) 
      ? new THREE.IcosahedronGeometry(Math.random() * 2.2 + 1.2, 0)
      : new THREE.TorusGeometry(Math.random() * 2 + 1.2, 0.4, 12, 24);

    const mat = materials[i % materials.length];
    const mesh = new THREE.Mesh(geo, mat);

    mesh.position.set(
      (Math.random() - 0.5) * 60,
      (Math.random() - 0.5) * 45,
      (Math.random() - 0.5) * 15
    );

    mesh.userData = {
      rotX: (Math.random() - 0.5) * 0.006,
      rotY: (Math.random() - 0.5) * 0.006,
      floatSpeed: Math.random() * 0.4 + 0.3,
      startY: mesh.position.y
    };

    group.add(mesh);
    meshes.push(mesh);
  }

  let targetMouseX = 0, targetMouseY = 0, curMouseX = 0, curMouseY = 0;

  window.addEventListener('mousemove', (e) => {
    targetMouseX = (e.clientX / window.innerWidth - 0.5) * 2;
    targetMouseY = -(e.clientY / window.innerHeight - 0.5) * 2;
  }, { passive: true });

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  let clock = new THREE.Clock();

  function animate() {
    requestAnimationFrame(animate);
    const elapsed = clock.getElapsedTime();

    curMouseX += (targetMouseX - curMouseX) * 0.04;
    curMouseY += (targetMouseY - curMouseY) * 0.04;

    group.rotation.y = curMouseX * 0.12;
    group.rotation.x = -curMouseY * 0.12;

    meshes.forEach((m) => {
      m.rotation.x += m.userData.rotX;
      m.rotation.y += m.userData.rotY;
      m.position.y = m.userData.startY + Math.sin(elapsed * m.userData.floatSpeed) * 1.2;
    });

    renderer.render(scene, camera);
  }

  animate();
}
