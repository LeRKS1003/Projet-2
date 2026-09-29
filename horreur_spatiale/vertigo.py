# -*- coding: utf-8 -*-
"""
vertigo.py — Crises de vertige après la révélation du disque dur.

L'infection s'aggrave : par intermittence (toutes les 30 à 90 s environ,
plus souvent quand la grande créature est proche ou pendant l'alerte), le
joueur fait une crise de 3 à 8 secondes :

  * image : la caméra tangue lentement, l'horizon s'incline, le champ de
    vision « respire », flou sur les bords, léger dédoublement, couleurs
    désaturées (rendu secondaire à demi-résolution + petit shader, actif
    seulement pendant la crise) ;
  * son : tout devient étouffé (« sous l'eau »), sifflement d'oreilles,
    bourdonnement à 7 Hz plus fort, respiration du joueur ;
  * contrôles : déplacement qui dérive sur le côté, visée instable,
    impossible de courir ; le joueur peut trébucher (la caméra tombe à
    moitié puis se relève) ;
  * manette : vibrations lentes et irrégulières.

Accessibilité : ces effets peuvent donner le mal des transports. Leur
intensité se règle dans config.py (VERTIGO_INTENSITY) et dans le menu pause
(Désactivé / Faible / Normal / Fort).
"""
import math
import random

from panda3d.core import CardMaker, Shader, TransparencyAttrib, Texture
from ursina import camera, color, application, window

import config as C

ORDER = ["desactive", "faible", "normal", "fort"]
LABELS = {"desactive": "Désactivé", "faible": "Faible", "normal": "Normal", "fort": "Fort"}

# ----------------------------------------------------------------------------
# SHADER DE L'ÉCRAN DE VERTIGE (flou des bords, dédoublement, désaturation)
# ----------------------------------------------------------------------------
_VERT = """
#version 140
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uv;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uv = p3d_MultiTexCoord0;
}
"""

_FRAG = """
#version 140
uniform sampler2D p3d_Texture0;
uniform float level;      // intensité de la crise (0..1.5)
uniform vec2 ghost;       // décalage de l'image dédoublée
uniform float aspect;
in vec2 uv;
out vec4 frag;

vec3 tap(vec2 p) { return texture(p3d_Texture0, clamp(p, vec2(0.001), vec2(0.999))).rgb; }

void main() {
    vec2 c = (uv - 0.5) * vec2(aspect, 1.0);
    float r = length(c);
    float edge = smoothstep(0.22, 0.75, r);
    // flou d'autant plus fort qu'on s'éloigne du centre
    float rad = (0.002 + 0.014 * edge) * level;
    vec3 blur = tap(uv) * 0.2;
    blur += (tap(uv + vec2(rad, 0.0)) + tap(uv - vec2(rad, 0.0)) +
             tap(uv + vec2(0.0, rad)) + tap(uv - vec2(0.0, rad))) * 0.12;
    blur += (tap(uv + vec2(rad, rad)) + tap(uv - vec2(rad, rad)) +
             tap(uv + vec2(rad, -rad)) + tap(uv - vec2(rad, -rad))) * 0.08;
    // dédoublement : une seconde image légèrement décalée
    vec3 dbl = tap(uv + ghost);
    vec3 col = mix(blur, dbl, 0.45);
    // désaturation
    float lum = dot(col, vec3(0.3, 0.59, 0.11));
    col = mix(col, vec3(lum) * vec3(0.95, 1.0, 1.03), clamp(0.8 * level, 0.0, 0.9));
    float a = clamp(level * (0.28 + 0.62 * edge), 0.0, 0.92);
    frag = vec4(col, a);
}
"""


class VertigoScreen:
    """Rendu secondaire de la scène (demi-résolution) affiché par-dessus avec le shader de vertige."""

    def __init__(self):
        base = application.base
        self.ok = False
        self.active = False
        try:
            w = max(64, int(base.win.getXSize() * C.VERTIGO_BUFFER_SCALE))
            h = max(64, int(base.win.getYSize() * C.VERTIGO_BUFFER_SCALE))
            self.tex = Texture("vertigo_tex")
            self.buf = base.win.makeTextureBuffer("vertigo_buf", w, h, self.tex)
            if self.buf is None:
                raise RuntimeError("tampon hors écran indisponible")
            self.buf.setSort(-40)
            self.buf.setClearColor((0, 0, 0, 1))
            self.cam = base.makeCamera(self.buf, lens=base.camLens)
            self.cam.reparentTo(base.cam)             # suit exactement la caméra principale
            self.buf.setActive(False)
            cm = CardMaker("vertigo_card")
            ar = window.aspect_ratio
            cm.setFrame(-ar / 2, ar / 2, -.5, .5)
            self.card = camera.ui.attachNewNode(cm.generate())
            self.card.setTexture(self.tex)
            self.card.setShader(Shader.make(Shader.SL_GLSL, _VERT, _FRAG))
            self.card.setShaderInput("level", 0.0)
            self.card.setShaderInput("ghost", (0.0, 0.0))
            self.card.setShaderInput("aspect", ar)
            self.card.setTransparency(TransparencyAttrib.MAlpha)
            self.card.setDepthTest(False)
            self.card.setDepthWrite(False)
            self.card.setBin("background", 5)          # sous le HUD
            self.card.setPos(0, 0, 0)
            self.card.hide()
            self.ok = True
        except Exception as exc:                        # carte graphique trop ancienne : effets restants seulement
            print("[vertiges] écran de vertige indisponible :", exc)

    def set(self, level, ghost):
        if not self.ok:
            return
        on = level > .01
        if on != self.active:
            self.active = on
            self.buf.setActive(on)
            if on:
                self.card.show()
            else:
                self.card.hide()
        if on:
            self.card.setShaderInput("level", float(level))
            self.card.setShaderInput("ghost", (float(ghost[0]), float(ghost[1])))
            self.card.setShaderInput("aspect", float(window.aspect_ratio))

    def destroy(self):
        if not self.ok:
            return
        base = application.base
        self.card.removeNode()
        self.cam.removeNode()
        base.graphicsEngine.removeWindow(self.buf)
        self.ok = False


class Vertigo:
    def __init__(self, game):
        self.game = game
        # réglage conservé d'une partie à l'autre (menu pause), sinon celui de config.py
        st = getattr(game, "vertigo_setting", None) or C.VERTIGO_INTENSITY
        self.setting = st if st in ORDER else "normal"
        self.t = 0.0
        self.timer = C.VERTIGO_FIRST_DELAY
        self.crisis = 0.0            # temps restant de la crise en cours
        self.crisis_len = 0.0
        self.env = 0.0               # enveloppe 0..1 (montée / descente douces)
        self.level = 0.0             # intensité effective (enveloppe x réglage)
        self.forced = False          # F11 : crise même avant la révélation
        self.stumble_t = -1.0        # trébuchement en cours (secondes écoulées)
        self._stumble_at = None
        self._rumble_t = 0.0
        self._drift_phase = random.uniform(0, 6.28)
        self.screen = VertigoScreen() if C.VERTIGO_SCREEN_FX else None
        a = game.audio
        self.ring = a.loop("vertigo_ring", "vertigo_ring", .35, ambient=True)
        self.muffle = a.loop("vertigo_muffle", "vertigo_muffle", .6, ambient=True)
        self.breath = a.loop("vertigo_breath", "vertigo_breath", .55)
        a.muffle_exempt |= {"vertigo_ring", "vertigo_muffle", "vertigo_breath", "sinus_low", "breath", "heartbeat"}

    # ------------------------------------------------------------------
    @property
    def mult(self):
        return C.VERTIGO_LEVELS.get(self.setting, 1.0)

    def label(self):
        return LABELS.get(self.setting, "Normal")

    def cycle_setting(self):
        """Menu pause : Désactivé -> Faible -> Normal -> Fort -> Désactivé..."""
        i = ORDER.index(self.setting) if self.setting in ORDER else 2
        self.setting = ORDER[(i + 1) % len(ORDER)]
        self.game.vertigo_setting = self.setting
        if self.mult <= 0:
            self.stop()
        return self.label()

    def enabled(self):
        g = self.game
        if self.mult <= 0:
            return False
        rv = g.revelation
        return self.forced or (rv is not None and rv.done)

    def guide_instability(self):
        """Pour le guidage : 0 hors crise, jusqu'à 1 au plus fort."""
        return min(1.0, self.level)

    # ------------------------------------------------------------------
    def start_crisis(self, forced=False):
        g = self.game
        if forced:
            self.forced = True
        if self.mult <= 0:
            g.hud.message("[vertiges désactivés dans le menu pause]", color.yellow)
            return
        self.crisis_len = random.uniform(*C.VERTIGO_DURATION)
        self.crisis = self.crisis_len
        self._drift_phase = random.uniform(0, 6.28)
        self._stumble_at = (random.uniform(.25, .6) * self.crisis_len
                            if random.random() < C.VERTIGO_STUMBLE_CHANCE else None)
        g.audio.play("heartbeat", .6, .85, ignore_duck=True)
        if random.random() < .5:
            g.hud.message("Ta vision se trouble...", color.rgb(.7, .75, .8))

    def _interval(self):
        return random.uniform(*C.VERTIGO_INTERVAL)

    def update(self, dt):
        g = self.game
        p = g.player
        self.t += dt
        playing = g.state == "fps" and p is not None and p.alive and not g.paused
        if playing and self.enabled():
            # plus fréquent quand la créature est proche ou pendant l'alerte
            speed = 1.0
            cr = g.creature
            if cr is not None and cr.visible and math.hypot(cr.x - p.x, cr.z - p.z) < C.VERTIGO_NEAR_DIST:
                speed = C.VERTIGO_NEAR_FACTOR
            if g.horror is not None and g.horror.active:
                speed = max(speed, C.VERTIGO_NEAR_FACTOR)
            if self.crisis <= 0:
                self.timer -= dt * speed
                if self.timer <= 0:
                    self.timer = self._interval()
                    self.start_crisis()
        # enveloppe de la crise
        if self.crisis > 0 and playing:
            self.crisis -= dt
            elapsed = self.crisis_len - self.crisis
            target = min(1.0, elapsed / .9) * min(1.0, max(0.0, self.crisis) / 1.3)
            if self._stumble_at is not None and elapsed >= self._stumble_at:
                self._stumble_at = None
                self._start_stumble()
        else:
            self.crisis = 0.0
            target = 0.0
        self.env += (target - self.env) * min(1.0, dt * 4)
        if self.env < .003 and target == 0:
            self.env = 0.0
        # hors exploration (menu, cinématique...) : aucun effet
        self.level = self.env * self.mult if g.state == "fps" else 0.0
        if self.stumble_t >= 0:
            self.stumble_t += dt
            if self.stumble_t > C.VERTIGO_STUMBLE_TIME:
                self.stumble_t = -1.0
        self._apply_audio(dt)
        self._apply_screen()
        self._apply_rumble(dt)

    def _start_stumble(self):
        g = self.game
        self.stumble_t = 0.0
        g.audio.play("rustle", .7, .8)
        g.audio.play(f"step{random.randint(0, 3)}", .6, .8)
        g.audio.play("breath", .6, .9, ignore_duck=True)
        g.inp.rumble(.7, .2, 350)

    # ------------------------------------------------------------------
    # EFFETS
    # ------------------------------------------------------------------
    def stumble_k(self):
        """0 debout -> 1 à moitié tombé (courbe du trébuchement)."""
        if self.stumble_t < 0:
            return 0.0
        t = self.stumble_t
        T = C.VERTIGO_STUMBLE_TIME
        if t < .35:
            return (t / .35) ** 2
        if t < .65:
            return 1.0
        k = (t - .65) / max(.05, T - .65)
        return max(0.0, 1 - k * k * (3 - 2 * k))

    def camera_offsets(self):
        """(tangage, lacet, roulis, delta FOV, delta hauteur des yeux) à ajouter à la caméra."""
        L = self.level
        sk = self.stumble_k() * min(1.0, self.mult)
        if L <= 0 and sk <= 0:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        t = self.t
        pitch = (math.sin(t * .83) * 3.5 + math.sin(t * 2.3 + 1) * 1.2) * L + sk * 22
        yaw = (math.sin(t * .61 + 2) * 4.0 + math.sin(t * 1.7) * 1.0) * L
        roll = (math.sin(t * .47) * 9.0 + math.sin(t * 1.3 + .5) * 2.0) * L + sk * 9
        fov = math.sin(t * 1.1) * 7.0 * L + 4 * L
        dy = -sk * .75
        return pitch, yaw, roll, fov, dy

    def drift(self):
        """Dérive latérale (m/s) et facteur de vitesse pendant la crise."""
        L = self.level
        if L <= 0 and self.stumble_t < 0:
            return 0.0, 1.0
        side = math.sin(self.t * .9 + self._drift_phase) * .9 * L
        speed = 1.0 - .25 * min(1.0, L)
        if self.stumble_t >= 0:
            speed *= .15
        return side, speed

    def blocks_running(self):
        return self.level > .12 or self.stumble_t >= 0

    def _apply_audio(self, dt):
        g = self.game
        L = min(1.0, self.level)
        g.audio.muffle = 1.0 - .62 * L
        self.ring.set(L * .9, fade=2.5)
        self.muffle.set(L, fade=2.5)
        self.breath.set(L * .9, fade=2.0)
        # bourdonnement à 7 Hz plus fort
        if g.hallu is not None and L > .01 and (g.revelation is None or not g.revelation.active):
            g.hallu.hum.set(max(C.HALLU_HUM * g.hallu.infection, .75 * L), fade=1.5)

    def _apply_screen(self):
        if self.screen is None:
            return
        L = self.level
        t = self.t
        gx = math.sin(t * 1.9) * .006 * L + math.sin(t * 5.3) * .002 * L
        gy = math.cos(t * 1.4) * .004 * L
        self.screen.set(L, (gx, gy))

    def _apply_rumble(self, dt):
        L = min(1.0, self.level)
        if L <= .05:
            return
        self._rumble_t -= dt
        if self._rumble_t <= 0:
            self._rumble_t = random.uniform(.5, 1.4)
            self.game.inp.rumble(random.uniform(.15, .45) * L, random.uniform(0, .12) * L,
                                 int(random.uniform(250, 650)))

    # ------------------------------------------------------------------
    def stop(self):
        """Fin de partie / cinématique : tout revient à la normale."""
        self.crisis = 0.0
        self.env = self.level = 0.0
        self.stumble_t = -1.0
        g = self.game
        g.audio.muffle = 1.0
        for lp in (self.ring, self.muffle, self.breath):
            lp.set(0, fade=4)
        if self.screen is not None:
            self.screen.set(0, (0, 0))

    def destroy(self):
        self.stop()
        g = self.game
        for key in ("vertigo_ring", "vertigo_muffle", "vertigo_breath"):
            g.audio.stop_loop(key)
        if self.screen is not None:
            self.screen.destroy()
            self.screen = None
