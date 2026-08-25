import sys
from pathlib import Path
KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "src"))

from anlama import anla
from ayristirici import ayristir
from denetci import Denetci
from llm_istemci import istemci_olustur
from okuyucu import oku
from veri_yapisi import Dosya

NUMARALAR = ("258 045 254 025 124 117 058 261 069 263 007 192 053 044 288 130 "
             "266 046 170 271 056 289 028 236 003 099 165 241 209 177 238 153 "
             "067 024 214 068 198 156 034 054").split()

istemci = istemci_olustur(KOK / "yapilandirma.qwen.json")
denetci = Denetci()
klasor = KOK / "deneyler" / "adim4" / "belgeler_pdf"

for no in NUMARALAR:
    r = oku(klasor / f"belge_{no}.pdf")
    if r.hata or not r.satirlar:
        continue
    a = ayristir(r.satirlar, r.ayrilmis.dipnot_bulundu if r.ayrilmis else None)
    d = Dosya(); d.ustveri = a.ustveri; d.metin = r.govde
    an = anla(r.govde, a, istemci)
    d.siniflandirma, d.icerik = an.siniflandirma, an.icerik
    denetci.calistir(d)
    istenecek = [e for e in d.icerik.eksik_alanlar
                 if e.talep_edilebilir and not e.giderildi and e.soru]
    if istenecek:
        print(f"belge_{no}  " + " · ".join(f"{e.kural_id}:{e.alan}" for e in istenecek))