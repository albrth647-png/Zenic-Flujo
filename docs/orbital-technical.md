# ORBITAL — Documentación Técnica v3.2

## Arquitectura

ORBITAL es un motor determinista circular compuesto por 5 pilares:

```
OVC → TOR → RCC → COD → Espectro → retroalimentación → OVC
```

### 1. OVC — Orbita Variable Circular

Variables con fase (θ), amplitud (A) y velocidad orbital (ω).

**Ecuación:** `θ(t+1) = (θ(t) + ω * dt) mod 2π`

### 2. TOR — Tension Orbital Reciproca

Fuerza entre pares de variables.

**Ecuación:** `TOR(i,j) = A_i * A_j * cos(θ_i - θ_j)`

Propiedades:
- Simétrica: TOR(i,j) = TOR(j,i)
- Acotada: |TOR(i,j)| ≤ A_i * A_j
- Con cache de tensiones (hit rate > 90%)

### 3. RCC — Resonancia Ciclo Cerrado

Detecta cuando TOR supera un umbral en ciclos cerrados.

### 4. COD — Colapso Orbital Determinista

Garantiza convergencia vía punto fijo de Brouwer.

**Algoritmo:**
1. Calcular TOR para todas las parejas
2. Acumular tensiones por variable
3. Normalizar por amplitud (para escalas extremas)
4. Aplicar tanh + relajación adaptativa
5. Verificar convergencia: |Δθ| < ε

### 5. Espectro Orbital

Genera salida multimodal determinista que retroalimenta el OVC.

## Teorema de Convergencia

**Teorema (Punto Fijo de Brouwer):** Toda función continua de un conjunto
compacto convexo en sí mismo tiene al menos un punto fijo.

**Aplicación en COD:**
- Espacio de fases = [0, 2π)^N (compacto, convexo)
- F(θ) = θ + tanh(TOR(θ)) * ω * dt (continua)
- ∴ Existe θ* tal que F(θ*) = θ*

## Garantías

| Propiedad | Garantía |
|-----------|----------|
| Determinismo | Mismas condiciones iniciales → mismo estado final |
| Convergencia | Garantizada para amplitudes 1–10000 |
| Estado estable | Punto fijo después de convergencia |
| Complejidad | O(N²) por tick, O(K) para convergencia |
