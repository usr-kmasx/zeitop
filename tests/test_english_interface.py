import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class TestEnglishInterface(unittest.TestCase):
    def test_html_and_js_are_english_only(self):
        html=(ROOT/"ui"/"index.html").read_text(encoding="utf-8")
        js=(ROOT/"ui"/"main.js").read_text(encoding="utf-8")
        app=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertIn('lang="en"',html)
        self.assertIn('aria-label="Frame-time history graph"', html)
        self.assertFalse(re.search(r"[À-ÖØ-öø-ÿ]", html), "Accented UI string remains")
        for token in ("FT AVERAGE","TARGET","WAITING FOR GAME","LAST 100 SAMPLES","Frame-time graph","Enable limiter","Copy Steam launch command","Settings (coming soon)"):
            self.assertIn(token,html)
        for token in ("GAME CONNECTED","WAITING FOR GAME","Settings coming soon","Run Zeitop as a desktop app","Disable limiter","Enable limiter"):
            self.assertIn(token,js)
        self.assertIn("Command copied",app)
        for text in (html,js,app):
            self.assertFalse(re.search(r"Ativar|Desativar|Copiar|Configurações|Fechar|MÉDIO|ALVO|AGUARDANDO|JOGO|ÚLTIMAS|Comando copiado|Falha ao copiar|Execute pelo app",text,re.IGNORECASE), text)
