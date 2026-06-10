/**
 * ORBITAL — Visualizador de Espectro Orbital
 * Animación en tiempo real del ciclo ORBITAL con canvas
 * OVC → TOR → RCC → COD → Espectro
 */
class OrbitalVisualizer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.variables = [];
        this.torValues = [];
        this.tick = 0;
        this.dpr = window.devicePixelRatio || 1;
        this.resize();
        this.running = false;
        this.animationId = null;
    }

    resize() {
        const rect = this.canvas.getBoundingClientRect();
        this.canvas.width = rect.width * this.dpr;
        this.canvas.height = rect.height * this.dpr;
        this.ctx.scale(this.dpr, this.dpr);
        this.width = rect.width;
        this.height = rect.height;
        this.centerX = this.width / 2;
        this.centerY = this.height / 2;
        this.radius = Math.min(this.width, this.height) * 0.35;
    }

    /**
     * Actualiza datos desde API
     */
    async fetchData() {
        try {
            const res = await fetch('/api/orbital/status');
            if (!res.ok) return;
            const data = await res.json();
            if (data.variables) {
                this.variables = Object.entries(data.variables).map(([name, v]) => ({
                    name,
                    theta: v.theta || 0,
                    amplitude: v.amplitude || 1,
                    velocity: v.velocity || 0.1,
                    value: v.value || 0
                }));
            }
            if (data.tor) {
                this.torValues = data.tor;
            }
            this.tick = data.tick || 0;
        } catch (e) {
            // Silently fail, keep last state
        }
    }

    /**
     * Inicia la animación
     */
    start(intervalMs = 1000) {
        if (this.running) return;
        this.running = true;
        this.fetchData();
        const animate = () => {
            if (!this.running) return;
            this.tick++;
            // Advance phases
            this.variables.forEach(v => {
                v.theta = (v.theta + v.velocity * 0.05) % (Math.PI * 2);
            });
            this.draw();
            this.animationId = requestAnimationFrame(animate);
        };
        // Fetch data periodically
        setInterval(() => this.fetchData(), intervalMs);
        animate();
    }

    stop() {
        this.running = false;
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
    }

    /**
     * Dibuja el espectro orbital completo
     */
    draw() {
        const ctx = this.ctx;
        const { width, height, centerX, centerY, radius } = this;

        // Clear
        ctx.clearRect(0, 0, width, height);

        // Get computed theme colors
        const style = getComputedStyle(document.documentElement);
        const primary = style.getPropertyValue('--primary').trim() || '#6366f1';
        const success = style.getPropertyValue('--success').trim() || '#22c55e';
        const warning = style.getPropertyValue('--warning').trim() || '#f59e0b';
        const text = style.getPropertyValue('--text').trim() || '#e0e0e0';
        const muted = style.getPropertyValue('--text-muted').trim() || '#888';
        const bgCard = style.getPropertyValue('--bg-card').trim() || '#1a1a1a';

        if (this.variables.length === 0) {
            ctx.fillStyle = muted;
            ctx.font = '14px -apple-system, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Esperando datos orbitales...', centerX, centerY);
            return;
        }

        // ── Draw orbital rings ──────────────────────────
        for (let i = 0; i < 3; i++) {
            const r = radius * (0.3 + i * 0.25);
            ctx.beginPath();
            ctx.arc(centerX, centerY, r, 0, Math.PI * 2);
            ctx.strokeStyle = `rgba(99, 102, 241, ${0.1 + i * 0.05})`;
            ctx.lineWidth = 1;
            ctx.stroke();
        }

        // ── Draw TOR connections (edges) ────────────────
        const varPositions = this.variables.map((v, i) => {
            const angle = v.theta - Math.PI / 2;
            const dist = radius * (0.4 + (v.amplitude % 100) / 200);
            return {
                x: centerX + Math.cos(angle) * dist,
                y: centerY + Math.sin(angle) * dist,
                ...v
            };
        });

        // Draw TOR lines between connected variables
        for (let i = 0; i < varPositions.length; i++) {
            for (let j = i + 1; j < varPositions.length; j++) {
                const tor = this.torValues.find(
                    t => t.variable_i === varPositions[i].name && t.variable_j === varPositions[j].name
                );
                if (!tor) continue;
                const intensity = Math.abs(tor.tor_value || 0) / 1000;
                const alpha = Math.min(0.6, Math.max(0.05, intensity));
                const isPositive = (tor.tor_value || 0) >= 0;

                ctx.beginPath();
                ctx.moveTo(varPositions[i].x, varPositions[i].y);
                ctx.lineTo(varPositions[j].x, varPositions[j].y);
                ctx.strokeStyle = isPositive
                    ? `rgba(34, 197, 94, ${alpha})`
                    : `rgba(239, 68, 68, ${alpha})`;
                ctx.lineWidth = Math.max(1, alpha * 4);
                ctx.stroke();
            }
        }

        // ── Draw variables as orbiting particles ────────
        varPositions.forEach((v, i) => {
            const hue = (i / this.variables.length) * 360;
            const size = 8 + (v.amplitude % 50) / 10;
            const glow = 15 + (v.amplitude % 50) / 5;

            // Glow
            const gradient = ctx.createRadialGradient(
                v.x, v.y, 0, v.x, v.y, glow
            );
            gradient.addColorStop(0, `hsla(${hue}, 80%, 60%, 0.4)`);
            gradient.addColorStop(1, `hsla(${hue}, 80%, 60%, 0)`);
            ctx.fillStyle = gradient;
            ctx.beginPath();
            ctx.arc(v.x, v.y, glow, 0, Math.PI * 2);
            ctx.fill();

            // Particle
            ctx.beginPath();
            ctx.arc(v.x, v.y, size, 0, Math.PI * 2);
            ctx.fillStyle = `hsl(${hue}, 80%, 60%)`;
            ctx.fill();

            // Label
            ctx.fillStyle = text;
            ctx.font = '11px -apple-system, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(v.name, v.x, v.y + size + 14);

            // Value
            ctx.fillStyle = muted;
            ctx.font = '9px -apple-system, sans-serif';
            ctx.fillText(v.value.toFixed(2), v.x, v.y + size + 26);
        });

        // ── Tick counter ────────────────────────────────
        ctx.fillStyle = muted;
        ctx.font = '11px -apple-system, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(`Tick #${this.tick} · ${this.variables.length} vars`, 12, 20);
    }
}
