# minecraft-agent

Oyun oynayarak öğrenen bir bot sistemi. İlk oyun Minecraft; çekirdek oyundan bağımsız, her oyun bir eklenti.

Softito Yapay Zeka Eğitimi bireysel projesi: "Minecraft'ta Öğrenen Ajan" (Voyager benzeri, beceri kütüphanesi, Mineflayer + LLM). Teslim: 2026-11-19.

> **Durum:** tasarım tamamlandı, kod aşaması başlıyor. Kurulum ve kullanım adımları kod geldikçe buraya eklenecek.

## Ana fikirler

- **Oynayarak öğrenme:** bot görev seçer, beceri kodu yazar, oyunda dener, sonucu bağımsız bir kontrolle doğrular ve başarılı beceriyi kütüphanesine ekler. Ana iddia: öğrenilmiş kütüphane, botun hiç görmediği dünyalarda başarıyı düşürmeden süreyi ve LLM çağrısını azaltır.
- **Katmanlı karar:** düz kod (refleks, acil tehlike) → hızlı karar modeli (TypeSafe Jev / yerel) → frontier LLM (Claude Sonnet 5.5 / Haiku 5.5).
- **Oyun hafızası:** ev, portal, köy, maden konumları ve durumları; tükenmiş madene geri gitmez.
- **Oynayarak öğretme:** oyuncu bir işi gösterir, bot bunu test edilmiş bir beceriye çevirir.
- **AFK komutları:** "git demir kaz, envanter dolunca eve dön" gibi koşullu görevler.

## Belgeler

- [docs/research.md](docs/research.md): araştırma ve tasarımın tamamı
- [AGENTS.md](AGENTS.md): kararlar, mimari, kurallar, çalışma akışı
- [docs/notes.md](docs/notes.md): notlar ve açık sorular
- [docs/reviews/](docs/reviews/): dış tasarım incelemeleri
