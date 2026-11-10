shader_type canvas_item;
// ZENITH — efeitos animados de fundo (Estúdio de Aparência).
// Um shader só, escolhido por `efeito`. O tempo `t` vem do script (limitado a 30 FPS e pausado
// com a janela em segundo plano) — por isso NÃO usamos TIME aqui.
// Segurança: tudo é suave e lento; nenhum efeito pisca (nada passa de ~0,5 ciclo por segundo).
//  0 nenhum · 1 gradiente que desliza · 2 arco-íris · 3 respiração · 4 fogo · 5 aurora · 6 plasma
//  7 tinta (cor some e vira outra) · 8 borda neon que anda · 9 chuva de partículas · 10 estrelas · 11 varredura

uniform int efeito = 1;
uniform vec4 c1 : source_color = vec4(0.0, 0.85, 1.0, 1.0);
uniform vec4 c2 : source_color = vec4(1.0, 0.31, 0.64, 1.0);
uniform vec4 c3 : source_color = vec4(0.0, 0.9, 0.66, 1.0);
uniform vec4 c4 : source_color = vec4(0.5, 0.3, 1.0, 1.0);
uniform int ncores = 2;
uniform float t = 0.0;
uniform float intensidade : hint_range(0.0, 1.0) = 0.6;
uniform float opacidade : hint_range(0.0, 1.0) = 1.0;
uniform vec2 tamanho = vec2(400.0, 300.0);

vec3 cor_i(int i) {
	if (i == 0) return c1.rgb;
	if (i == 1) return c2.rgb;
	if (i == 2) return c3.rgb;
	return c4.rgb;
}

// x em [0,1): percorre as cores em círculo, com transição suave
vec3 paleta(float x) {
	int n = clamp(ncores, 2, 4);
	float p = fract(x) * float(n);
	int i = int(floor(p));
	float f = smoothstep(0.0, 1.0, p - float(i));
	return mix(cor_i(i % n), cor_i((i + 1) % n), f);
}

float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

float ruido(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash21(i);
	float b = hash21(i + vec2(1.0, 0.0));
	float c = hash21(i + vec2(0.0, 1.0));
	float d = hash21(i + vec2(1.0, 1.0));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float a = 0.5;
	for (int i = 0; i < 4; i++) {
		v += a * ruido(p);
		p = p * 2.03 + vec2(1.7, 9.2);
		a *= 0.5;
	}
	return v;
}

vec3 hsv2rgb(vec3 c) {
	vec3 k = clamp(abs(fract(c.x + vec3(0.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0) - 1.0, 0.0, 1.0);
	return c.z * mix(vec3(1.0), k, c.y);
}

void fragment() {
	vec2 uv = UV;
	float asp = tamanho.x / max(tamanho.y, 1.0);
	vec2 p = vec2((uv.x - 0.5) * asp, uv.y - 0.5);
	vec3 col = vec3(0.0);
	float a = 1.0;

	if (efeito == 1) {
		float x = uv.x * 0.7 + uv.y * 0.3 + t * 0.08;
		col = paleta(x);
		col = mix(vec3(0.05), col, 0.35 + 0.65 * intensidade);
	} else if (efeito == 2) {
		float h = fract(uv.x * 0.5 + uv.y * 0.2 + t * 0.06);
		col = hsv2rgb(vec3(h, 0.45 + 0.35 * intensidade, 0.35 + 0.5 * intensidade));
	} else if (efeito == 3) {
		float k = 0.5 + 0.5 * sin(t * 0.9);
		float r = length(p) * 1.2;
		col = mix(c1.rgb, c2.rgb, k);
		col *= mix(1.0, smoothstep(1.1, 0.1, r), 0.55);
		col = mix(vec3(0.04), col, 0.3 + 0.7 * intensidade);
	} else if (efeito == 4) {
		vec2 q = vec2(uv.x * 3.0 * asp * 0.5, uv.y * 3.0 + t * 0.7);   // a chama sobe
		float n = fbm(q + vec2(0.0, fbm(q * 1.3 + t * 0.15)));
		float h = clamp(uv.y * 1.25 - 0.1, 0.0, 1.0);                 // mais forte embaixo
		float f = clamp(n * 1.5 * h + h * h * 0.55 - 0.15, 0.0, 1.0);
		int nn = clamp(ncores, 2, 4);
		float pos = f * float(nn - 1);
		int i = int(floor(pos));
		vec3 fogo = mix(cor_i(min(i, 3)), cor_i(min(i + 1, 3)), smoothstep(0.0, 1.0, pos - float(i)));
		col = mix(vec3(0.02), fogo, smoothstep(0.02, 0.5, f) * (0.35 + 0.65 * intensidade));
	} else if (efeito == 5) {
		float v = 0.0;
		for (int i = 0; i < 3; i++) {
			float fi = float(i);
			float onda = sin(uv.x * (3.0 + fi) + t * (0.25 + 0.07 * fi) + fi * 1.7 + fbm(vec2(uv.x * 2.0, t * 0.1 + fi)) * 3.0);
			float faixa = 0.35 + 0.15 * fi + 0.12 * onda;
			v += smoothstep(0.28, 0.0, abs(uv.y - faixa)) * (0.6 - 0.12 * fi);
		}
		col = mix(vec3(0.02, 0.03, 0.07), paleta(uv.x * 0.6 + t * 0.03 + v * 0.25), clamp(v * (0.5 + 0.9 * intensidade), 0.0, 1.0));
	} else if (efeito == 6) {
		float v = sin(p.x * 5.0 + t * 0.5) + sin(p.y * 6.0 + t * 0.4) + sin((p.x + p.y) * 4.0 + t * 0.3) + sin(length(p) * 7.0 - t * 0.5);
		col = paleta(v * 0.125 + 0.5 + t * 0.02);
		col = mix(vec3(0.04), col, 0.3 + 0.7 * intensidade);
	} else if (efeito == 7) {
		float n = fbm(uv * vec2(asp, 1.0) * 1.4 + vec2(t * 0.04, -t * 0.03));
		float x = n * 1.1 + t * 0.015;
		col = paleta(x);
		col = mix(vec3(0.04), col, 0.3 + 0.7 * intensidade);
	} else if (efeito == 8) {
		vec2 px = uv * tamanho;
		float d = min(min(px.x, tamanho.x - px.x), min(px.y, tamanho.y - px.y));
		float larg = 1.5 + 4.0 * intensidade;
		float ring = smoothstep(larg, 0.0, d);
		float ang = atan(p.y, p.x) / 6.2831853 + 0.5;
		col = paleta(ang + t * 0.08);
		a = ring * (0.5 + 0.5 * intensidade);
		a = max(a, smoothstep(larg * 6.0, 0.0, d) * 0.12 * intensidade);
	} else if (efeito == 9) {
		float acc = 0.0;
		for (int i = 0; i < 3; i++) {
			float fi = float(i);
			float esc = 14.0 + fi * 10.0;
			vec2 g = vec2(uv.x * esc * asp, uv.y * esc + t * (0.5 + fi * 0.35));
			vec2 id = floor(g);
			vec2 f = fract(g) - 0.5;
			float h = hash21(id + fi * 17.0);
			vec2 off = vec2(h - 0.5, fract(h * 7.0) - 0.5) * 0.5;
			float ponto = smoothstep(0.17, 0.0, length(f - off));
			acc += ponto * step(0.55, h) * (0.9 - 0.2 * fi);
		}
		col = paleta(uv.y * 0.6 + t * 0.02);
		a = clamp(acc, 0.0, 1.0) * (0.35 + 0.65 * intensidade);
	} else if (efeito == 10) {
		float acc = 0.0;
		for (int i = 0; i < 2; i++) {
			float fi = float(i);
			float esc = 18.0 + fi * 14.0;
			vec2 g = vec2(uv.x * esc * asp, uv.y * esc);
			vec2 id = floor(g);
			vec2 f = fract(g) - 0.5;
			float h = hash21(id + fi * 31.0);
			float brilho = 0.5 + 0.5 * sin(t * (0.5 + h * 0.8) + h * 6.2831);
			float estrela = smoothstep(0.13, 0.0, length(f - (vec2(h, fract(h * 9.0)) - 0.5) * 0.6));
			acc += estrela * step(0.62, h) * (0.3 + 0.7 * brilho);
		}
		col = paleta(uv.x * 0.4 + t * 0.01);
		a = clamp(acc, 0.0, 1.0) * (0.4 + 0.6 * intensidade);
	} else if (efeito == 11) {
		float linha = 0.5 + 0.5 * sin((uv.y * tamanho.y) * 1.2 + t * 2.0);
		float faixa = smoothstep(0.1, 0.0, abs(fract(uv.y - t * 0.05) - 0.5) - 0.42);
		col = paleta(uv.x * 0.3 + t * 0.01);
		a = (linha * 0.10 + faixa * 0.16) * (0.4 + 0.6 * intensidade);
	}
	COLOR = vec4(col, a * opacidade);
}
