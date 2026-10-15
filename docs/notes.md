# Notlar

Fatih'in ve agentların ortak not defteri. Kısa tut; uzun araştırma `research.md`'ye, yarım iş `backlog.md`'ye gider.
Her notun başına tarih (YYYY-AA-GG) ve yazan (`Fatih` / agent adı) yaz. En yeni not en üstte.

---

## Açık sorular (Fatih'in cevabı bekleniyor)

- [ ] **"Mükemmel" hedeflerinin sayıları**: tanım karara bağlandı (kademeli); research.md §11'deki tablodaki eşikler (elmas kazma ≥8/10 seed, görev seti ≥%90, normal zorlukta 3 gün ≤1 ölüm, tepki ≤500 ms, kayıttan beceri ≥4/5, S1 noktaları kuralı geçmeli) uygun mu?
- [ ] **Kapsam**: Tek ajan yeterli mi, yoksa ileride çok ajanlı (MineCollab tarzı) bir uzantı da ister misin?

**Cevaplananlar**
- [x] 2026-10-15 · Fatih — **Teslim tarihi:** 5 hafta sonra, **2026-11-19**. Haftalık plan research.md §12.
- [x] 2026-10-15 · Fatih — **Çekirdek dili:** Python (agent önerisi de bu; Minecraft eklentisi TypeScript kalır). AGENTS.md karar 1.
- [x] 2026-10-15 · Fatih — **İkinci oyun:** Doom (ViZDoom), teslimden sonraki iş.
- [x] 2026-10-15 · Fatih — **Çalışma şekli:** kodu agent yazar, Fatih inceler/anlar; GitHub issue → PR akışı. AGENTS.md "Çalışma akışı".
- [x] 2026-10-15 · Fatih — **İnceleme soruları** (research.md §14.4, AGENTS.md kararları 5, 12, 15–19):
  - L2: Sonnet 5.5 varsayılan, Haiku metin işleri; kademe ve Opus S5'te ölçülecek.
  - Teslim kapsamı: **hepsi kalsın** (risk sıralamayla yönetilecek).
  - Ana iddia: oynayarak öğrenme.
  - "Mükemmel": kademeli (elmas + 3 gün + 25 görev ana; bilinmeyen dünyada Ender Dragon esnek).
  - Görünürlük: iki mod (adil değerlendirme + tam bilgi AFK).
  - Kayıt: aşamalı (v1 blueprint + makro, v2 davranışsal).
  - Mindcraft: parça ödünç al, üstüne kurma.
- [x] 2026-10-15 · Fatih — **Otonomi**: otomatik modda bot kullanıcıya asla soru sormaz, tamamen otonom karar verir. → research.md §5.7, AGENTS.md karar 9b
- [x] 2026-10-15 · Fatih — **Eklenti mimarisi**: sistem diğer oyunlara evrimleşecek; Minecraft bir eklenti. → research.md §5.1–5.4, AGENTS.md karar 9
- [x] 2026-10-15 · Fatih — **Yaratıcılık**: GPT-6 Astra creeper olayı gibi yaratıcı olmalıyız. → research.md §10
- [x] 2026-10-15 · Fatih — **Komutlar**: AFK'dayken doğal dil, ses veya pipeline ile "git maden kaz / düşman öldür / şunu bul". → research.md §9
- [x] 2026-10-15 · Fatih — **Beceriler**: çok iyi olmalı, hızın kaynağı bu. → research.md §8
- [x] 2026-10-15 · Fatih — **Hafıza**: RAG + oyun geçmişi, envanter, kararlar, ev/portal konumu, köyler, bulunan kaynaklar; tükenmiş madene gitmemeli. → research.md §7
- [x] 2026-10-15 · Fatih — **L2 modelleri**: Haiku 5.5 + Sonnet 5.5; Haiku önce, karmaşık/yanlışsa Sonnet. → research.md §6.8, AGENTS.md karar 5
- [x] 2026-10-15 · Fatih — **GPU**: `fatih-pc`'de RTX 5070 Ti var. → research.md §6.9
- [x] 2026-10-15 · Fatih — **Minecraft client**: gerçek oyunu kuracak.
- [x] 2026-10-15 · Fatih — **Aşama**: brainstorm; kod kısmına henüz girilmeyecek.
- [x] 2026-10-15 · Fatih — **Jev**: TypeSafe API anahtarı var. Yerel sınıflandırıcılar da test edilecek, hangisi iyiyse; oyuna özel sentetik veri + fine-tune da seçenek. → research.md §6.6–6.7
- [x] 2026-10-15 · Fatih — **Kayıt anlatımı**: sesli veya metin, ikisi de olabilir. → AGENTS.md karar 11b
- [x] 2026-10-15 · Fatih — **LLM bütçesi**: düşünme, kısıt değil. → AGENTS.md karar 5b

---

## Fatih'in notları

_(buraya yaz)_

---

## Agent notları

- **2026-10-15 · claude-code** — Dış inceleme (Opus 5.5 alt ajan + GPT-6-Astra Codex) tamamlandı; ham raporlar `docs/reviews/`, sentez research.md §14. Ortak ve yüksek güvenli 12 bulgu tasarıma işlendi: ayrı süreç sandbox, acil tehlike L0'da, eylem hakemi, bağımsız yüklemler, eğitim/test ayrımı ve istatistik, `world_instance_id`, counterfactual sadece pilot, eşikler sağlayıcı başına, ince eklenti çekirdeği, `approver` zaman aşımı yetki vermez, belge hataları. Fatih'in KARAR'larıyla çelişenler notes açık sorularında.
- **2026-10-15 · claude-code** — Malde'nin reposu: github.com/rmalde/minecraft-agent (End portalı önceden doğrulanmış, ejderha konumu sunucu sensörüyle okunuyor; Jev çağrı sıklığı belgelenmemiş). Claude Record a skill resmî sayfası: sadece Mac Cowork, ~10 dk, video/ses saklanmıyor; resmî sayfada takip sorusu yok.
- **2026-10-15 · claude-code** — Unsloth "Jev uyumlu, sadece adres değişir" iddiası doğrulanamadı (Decision API `jev-latest` isteklerini yönlendiriyor ama cevaplar Laya biçiminde). Eski notumdaki bu ifade yanlış.

- **2026-10-15 · claude-code** — Otonomi kararıyla belgedeki tüm "soru/onay" adımları kaldırıldı: AFK komutunda "Başlayayım mı?" yerine bilgi amaçlı geri okuma; kayıttan beceride takip soruları yerine "varsayımlarını bildir", Kaydet/Güncelle/At kararı doğrulama skoruyla otomatik. Literatür karşılığı: Feng ve ark. L5 Observer (kullanıcı sadece izler + acil durdurma).
- **2026-10-15 · claude-code** — Eklenti sözleşmesini Minecraft'a göre şekillendirme riski var. Önlem: ViZDoom eklentisini kâğıt üstünde sözleşmeye oturtarak erken kontrol (kod yazmadan).

- **2026-10-15 · claude-code** — GPT-6 Astra olayı düzeltmesi: kaynaklarda "ölmeyi bekledi" yok; olan şu: creeper sandığı ve yatağı patlattı, model saatlerce patates ekti, yeşil şeylerden ürktü (Vals AI, 141 saatlik yayın). "Depresyon" medyanın yorumu.
- **2026-10-15 · claude-code** — Önemli dış doğrulama: Ronak Malde 2026-09-20'de GPT-6 Astra (35 çağrı) + Jev (131 çağrı) + Mineflayer ile Ender Dragon'u 8 dk 43 sn'de, < $1'a kesti (peaceful, bilinen seed/rota). Bu bizim L2 + L1 + L0 tasarımının aynısı. Orijinal X postunu (@rronak_) ve repoyu bulmak faydalı olur; kod açık kaynaksa harness'ı incelemeye değer.
- **2026-10-15 · claude-code** — Vals CUA-Bench (sadece piksel + klavye/fare): hiçbir model Minecraft'ta demir bulamadı. Durum API'si yolumuzu destekliyor.
- **2026-10-15 · claude-code** — Beceri hızlandırmasının en büyük kaldıracı: genel `obtain(item, n)` tarif çözücüsü (kod). Voyager'ın LLM'e yazdırdığı yüzlerce craft/mine becerisinin yerine geçer.

- **2026-10-15 · claude-code** — Hafıza tasarımının ana fikri: "ev nerede" bir koordinat, "madene gideyim mi" bir hesap → bunlar vektör aramasıyla değil yapılandırılmış sorgu ve fayda hesabıyla çözülür. RAG sadece serbest metin geçmiş ("neden doğuyu bıraktık?") için. "Sadece RAG" kolu ablasyonda bu iddiayı test edecek.
- **2026-10-15 · claude-code** — Kademe uyarısı (Signed Rescue Routing, 2026): büyük model küçük modelin doğru cevabını da bozabilir → Haiku→Sonnet yükseltmesinin net faydası tetikleyici başına ölçülmeli.

- **2026-10-15 · claude-code** — Claude Record a skill ve Codex Record & Replay ayrıntılı incelendi (research.md §4.1–4.3). İkisi de çıktıyı **yorumlanan talimat** (SKILL.md) olarak üretiyor ve testi kullanıcıya bırakıyor. Bizim farkımız: oyunda kesin olay akışı + çalıştırılabilir kod beceri + niyet kartı + taze dünyada otomatik doğrulama.
- **2026-10-15 · claude-code** — Unsloth 2026-10-07'de "karar modeli" eğitimini yayımladı (Qwen3.5 0.8B–4B, Gemma 4 E4B; olasılık + kalibrasyon). ~~Decision API'si Jev uyumlu, sadece adres değişir~~ → **doğrulanmadı** (bkz. üstteki not).

- **2026-10-15 · claude-code** — Vizyon genişledi (Fatih): çok oyunlu bot + record a skill, ilk prototip Minecraft. research.md tek belge olarak yeniden yazıldı (§2 Jev, §3 genel oyun ajanları, §4 record a skill, §5 adaptör protokollü mimari, §6 "mükemmel" hedefleri).
- **2026-10-15 · claude-code** — Düzeltme: "Jev Doom'u bitirdi" iddiasını destekleyen kaynak yok. Resmî demo bir hız gösterisi; topluluk deneyi tek arenada elle yazılmış botla aynı skoru aldı (6.55 öldürme); açık replika MAP01'de 5 öldürme aldı, bölüm bitirdiği raporlanmadı. Asıl ders: navigasyon ve sayısal işler kodda, model sadece bağlamsal küçük kararda.
- **2026-10-15 · claude-code** — Minecraft'ta insan oyununu kaydedip Mineflayer becerisine çeviren hazır bir çalışma bulunamadı → record a skill bu projenin özgün katkısı olabilir. `minecraft-protocol` paketinde hazır `examples/proxy` örneği var (v1.68).

- **2026-10-15 · claude-code** — Makinede Java yok, Docker 28.3 var → Minecraft sunucusu için `itzg/minecraft-server` imajı en kolay yol. LM Studio kurulu (`~/.lmstudio/bin/lms`), Ollama yok → yerel model karşılaştırması LM Studio'nun OpenAI-uyumlu ucuyla yapılabilir. Node 22.23, Python 3.14.
- **2026-10-15 · claude-code** — `mineflayer@4.39.0` (2026-09-06) test edilen sürümler: 1.8.8 … 1.21.11, 26.1. Mindcraft ve minecraft-mcp-server 1.21.11'e kadar destekliyor → 1.21.11 en güvenli ortak nokta.
- **2026-10-15 · claude-code** — Voyager kaynak kodundan çıkan, kopyalamaya değer fikirler: (1) her denemede sadece `[system, human]` iki mesaj, geçmiş yerine "son kod + hata + eleştiri" gömülü → sabit bağlam boyu; (2) primitive'lerin gerçek implementasyonu ile LLM'e gösterilen sade sürümü ayrı dosyalarda (`control_primitives` vs `control_primitives_context`); (3) müfredat görsel doğrulama gerektiren görevleri (inşa/yerleştirme) bilinçli olarak yasaklıyor; (4) 15 görevden sonra peaceful → easy geçişi.
- **2026-10-15 · claude-code** — Voyager'ın zaafları (iyileştirme fırsatı): kod çıplak `eval` ile çalışıyor; başarı yargısı tamamen LLM'de; başarısız denemelerden kalıcı ders çıkarılmıyor; müfredat var olmayan eşyalar önerebiliyor; MC 1.19 + Azure login'e sabit.
- **2026-10-15 · claude-code** — Değerlendirme uyarısı: 2026 beceri literatürü (SkillsBench, "skills in the wild") becerilerin faydasının kırılgan olduğunu gösteriyor → beceri kütüphanesinin katkısını mutlaka "kütüphanesiz" ablasyonla kanıtlamalıyız, yoksa rapor iddiası boş kalır.
