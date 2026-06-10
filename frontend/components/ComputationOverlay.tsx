/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useRef } from 'react';

const ComputationOverlay: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    // ASCII-safe character set — avoids mojibake on limited-font systems
    const chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef.:;+-=[]{}|/<>@#$%&*~^'.split('');
    const fontSize = 10;
    const columns = Math.floor(width / fontSize);

    // Each drop has position, speed, and opacity variation
    const drops = Array.from({ length: columns }, () => ({
      y: Math.random() * -height,
      speed: 1.5 + Math.random() * 5,
      opacity: 0.1 + Math.random() * 0.4,
    }));

    const draw = (time: number) => {
      // Clear with slight persistence
      ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
      ctx.fillRect(0, 0, width, height);

      ctx.font = `${fontSize}px JetBrains Mono, monospace`;

      drops.forEach((drop, i) => {
        // Randomly pick a character
        const text = chars[Math.floor(Math.random() * chars.length)];

        const x = i * fontSize;
        const y = drop.y;

        // Gradient or glow effect for the data stream
        if (Math.random() > 0.995) {
          ctx.fillStyle = '#ffffff'; // Occasional highlight
          ctx.shadowBlur = 12;
          ctx.shadowColor = '#fff';
        } else {
          ctx.fillStyle = `rgba(255, 255, 255, ${drop.opacity})`;
          ctx.shadowBlur = 0;
        }

        ctx.fillText(text, x, y);

        // Update position
        drop.y += drop.speed;

        // Reset drop with new randomized properties
        if (drop.y > height) {
          drop.y = Math.random() * -100;
          drop.speed = 1.5 + Math.random() * 5;
          drop.opacity = 0.1 + Math.random() * 0.4;
        }
      });

      // Subtle scanning line effect
      const scanY = (time / 3) % height;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, scanY);
      ctx.lineTo(width, scanY);
      ctx.stroke();

      animationFrameId = requestAnimationFrame(draw);
    };

    const handleResize = () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    window.addEventListener('resize', handleResize);
    animationFrameId = requestAnimationFrame(draw);

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100dvh',
        zIndex: 1,
        pointerEvents: 'none',
        opacity: 0.7,
      }}
    />
  );
};

export default ComputationOverlay;
