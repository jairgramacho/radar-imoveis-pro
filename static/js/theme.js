// =============================================
// RADAR IMÓVEIS PRO — Theme: Particles + Cursor
// =============================================
(function() {
  'use strict';

  // === PARTICLES ===
  var particlesEl = document.querySelector('.radar-particles');
  if (!particlesEl) {
    particlesEl = document.createElement('div');
    particlesEl.className = 'radar-particles';
    particlesEl.style.cssText = 'position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:-1;';
    document.body.appendChild(particlesEl);
  }

  var particleCount = Math.min(40, Math.floor(window.innerWidth / 25));
  for (var i = 0; i < particleCount; i++) {
    var p = document.createElement('div');
    p.className = 'radar-particle';
    var size = 2 + Math.random() * 3;
    p.style.cssText =
      'position:absolute;' +
      'width:' + size + 'px;height:' + size + 'px;' +
      'background:#F28A1F;border-radius:50%;opacity:0;' +
      'left:' + (Math.random() * 100) + '%;' +
      'animation:radarFloat ' + (8 + Math.random() * 12) + 's linear infinite;' +
      'animation-delay:' + (Math.random() * -15) + 's;';
    particlesEl.appendChild(p);
  }

  // Inject keyframes if not already defined
  if (!document.getElementById('radar-particle-style')) {
    var style = document.createElement('style');
    style.id = 'radar-particle-style';
    style.textContent =
      '@keyframes radarFloat {' +
      '0%{transform:translateY(100vh) scale(0);opacity:0}' +
      '10%{opacity:0.2}' +
      '90%{opacity:0.2}' +
      '100%{transform:translateY(-10vh) scale(1);opacity:0}' +
      '}';
    document.head.appendChild(style);
  }

  // === CURSOR FOLLOWER ===
  var follower = document.querySelector('.cursor-follower');
  if (!follower && window.innerWidth > 768) {
    follower = document.createElement('div');
    follower.className = 'cursor-follower';
    document.body.appendChild(follower);

    var mouseX = 0, mouseY = 0;
    var folX = 0, folY = 0;

    document.addEventListener('mousemove', function(e) {
      mouseX = e.clientX;
      mouseY = e.clientY;
    });

    function animate() {
      folX += (mouseX - folX) * 0.1;
      folY += (mouseY - folY) * 0.1;
      if (follower) {
        follower.style.transform = 'translate(' + folX + 'px, ' + folY + 'px) translate(-50%, -50%)';
      }
      requestAnimationFrame(animate);
    }
    animate();

    // Hover effect on interactive elements
    document.addEventListener('mouseover', function(e) {
      var target = e.target.closest('a, button, .card, .imovel-card-link, .btn');
      if (target && follower) {
        follower.classList.add('hover');
      }
    });
    document.addEventListener('mouseout', function(e) {
      var target = e.target.closest('a, button, .card, .imovel-card-link, .btn');
      if (!target && follower) {
        follower.classList.remove('hover');
      }
    });
  }
})();
