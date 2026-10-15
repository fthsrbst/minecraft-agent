# minecraft-agent — Agent Talimatları

> **Tek kaynak bu dosyadır.** `CLAUDE.md` bu dosyaya bir sembolik bağdır (`CLAUDE.md -> AGENTS.md`);
> hangisini düzenlersen düzenle ikisi de aynı içeriği gösterir. Bağı bozma: `CLAUDE.md`'yi silip
> yerine normal dosya yazma. Bozulduysa: `ln -sf AGENTS.md CLAUDE.md`.

## Proje

**Farklı oyunları oynayabilen, öğrenen bir oyun botu sistemi. İlk prototip: Minecraft'ı mükemmel oynamak.**

- **Voyager döngüsü**: müfredat görev önerir → LLM beceri kodu yazar → kod oyunda çalışır → sonuç doğrulanır → beceri kütüphanesine eklenir.
- **System 1 / System 2**: yavaş LLM (plan, kod) + hızlı karar modeli (Jev veya yerel logit sınıflandırıcı; oyun akarken 2–10 Hz karar) + refleks kodu (yol bulma, nişan).
- **Record a skill**: insan oyunu bir kez gösterir (isteğe bağlı sesli anlatımla), sistem bunu test edilmiş parametreli bir beceriye çevirir.
- **Genellik**: çekirdek hiçbir oyunu bilmez; **Minecraft bir eklentidir**. Her oyun Game Plugin Protocol ile bağlanan bir eklentidir; sistem zamanla diğer oyunlara evrimleşir (research.md §5).
- **Ayarlanabilir otonomi**: `full` modda bot kullanıcıya **asla soru sormaz**; `approver`/`consult` modlarında sorabilir ama her soru zaman aşımlıdır ve bot asla kilitlenmez (research.md §5.7).

- Bağlam: Softito Yapay Zeka Eğitimi, bireysel proje (Zor seviye, #40 "Minecraft'ta Öğrenen Ajan"). Kurs teslimi Minecraft prototipidir; çok oyunluluk mimariyle hazırlanır.
- Teslimler: GitHub repo + README, çalışan demo (web/CLI), prompt ve model seçimi gerekçeleri, **değerlendirme raporu (≥20 test, başarı oranı, maliyet, gecikme)**, 3–5 dk demo videosu + sunum.
- Hub proje adı: `minecraft-agent` (kararlar/oturumlar hub'a bu adla yazılır).

## Belgeler (docs/)

| Dosya | Ne için | Kim yazar |
|---|---|---|
| [docs/research.md](docs/research.md) | **Tek araştırma belgesi**: Voyager + rakipler, Jev/System One, genel oyun ajanları, record a skill, mimari, model katmanları, oyun hafızası, beceri tasarımı, komut/pipeline, yaratıcılık/kişilik, "mükemmel" Minecraft hedefleri, yol haritası | Araştırma yapan agent |
| [docs/notes.md](docs/notes.md) | Fatih'in ve agentların notları, açık sorular, gözlemler | Herkes |
| [docs/reviews/](docs/reviews/) | Dış inceleme raporları (ham). Sentez research.md §14'te | İnceleme yapan ajanlar |
| [docs/backlog.md](docs/backlog.md) | **Yarım kalan işler** (agentlar oturum sonunda yazar) | Agentlar |
| `docs/backlog/<konu>.md` | Bir backlog maddesi büyürse alt-backlog dosyası | Agentlar |

Oturum başında: `docs/backlog.md` ve `docs/notes.md` → "Açık sorular" bölümünü oku.

## Kararlar

Durum: **ÖNERİ** = research.md'de önerildi, Fatih onayı bekliyor · **KARAR** = onaylandı.
Bir öneri onaylanınca burada KARAR'a çevir ve gerekçeyi hub'a `memory_save type=decision` ile yaz.

| # | Konu | Durum | İçerik |
|---|---|---|---|
| 0 | Vizyon | KARAR (Fatih, 2026-10-15) | Çok oyunlu bot sistemi; ilk prototip Minecraft'ı mükemmel oynamalı; record-a-skill özelliği olacak |
| 1 | Dil/çalışma zamanı | KARAR (Fatih, 2026-10-15) | **Çekirdek Python 3.13** (uv, ruff, pyright strict, pytest). **Minecraft eklentisi TypeScript** (Node 22, Mineflayer; beceri kodu TS + `tsc`). Doom eklentisi Python (ViZDoom). Eklentiler her zaman ayrı süreç, sürümlü JSON-RPC ile bağlanır |
| 2 | Bot kütüphanesi | ÖNERİ | `mineflayer@4.39.x` + pathfinder, collectblock, pvp, tool. **Uyarı:** eklentiler bayat (pathfinder 2023-09, pvp 2022-07, tool 2022-05; viewer 1.21.11'de 1.21.4 dokuları) → spike S1 ile doğrulanmadan KARAR olmaz |
| 3 | Minecraft sürümü | ÖNERİ | Java **1.21.11**, sabit; değiştirmek beceri kütüphanesi regresyonu gerektirir |
| 4 | Sunucu | ÖNERİ | Docker `itzg/minecraft-server`, `ONLINE_MODE=false`, sadece localhost, **RCON açık** (sadece değerlendirici/senaryo kurucu kullanır), ajan botu **op değil**, proxy için `enforce-secure-profile=false` |
| 5 | LLM (L2) | KARAR (Fatih, 2026-10-15, inceleme sonrası) | **Sonnet 5.5 varsayılan** (kod yazma/onarım, plan, kayıttan beceri, critic); **Haiku 5.5** yüksek hacimli metin işleri (özet, günlük, beceri açıklaması). Haiku→Sonnet kademesi ve Opus 5.5 spike **S5**'te ölçülür; kademe başarıda geri kalmayıp süre/maliyette belirgin kazanırsa varsayılan olur (research.md §6.8) |
| 5b | Bütçe | KARAR (Fatih, 2026-10-15) | LLM bütçesi kısıt değil; kalite öncelikli. Maliyet yine de her çağrıda ölçülür (rapor için) |
| 6 | Doğrulama | ÖNERİ | Önce deterministik yüklem, sonra L1 Noul, en son LLM critic. Yüklemler **koddan önce ve bağımsız** yazılır (test-önce sentez), negatif örneklerle sınanır; belirsiz = `unknown`, başarı sayılmaz. Critic görüşü doğrulanmış başarıyla aynı sınıfta tutulmaz |
| 7 | Beceri deposu | ÖNERİ | SQLite + yerel embedding + kosinüs top-k; beceri kodu `.js` dosyası olarak da saklanır |
| 8 | Kod yürütme | ÖNERİ (inceleme sonrası değişti) | `node:vm` **yeterli değil** (async zaman aşımı yok, olay döngüsü kilitlenir). Beceri kodu ayrı, anahtarsız, dosya/ağ kısıtlı, kaynak limitli yürütme sürecinde; oyun işlemleri izin denetimli primitive aracısıyla; dış watchdog; statik kurallar (`await`'siz döngü ve `bot.chat('/…')` yasak). Beceri dili TypeScript + `tsc` tip kontrolü (research.md §5.2, §14) |
| 9 | Oyun eklentisi | KARAR (Fatih): Minecraft bir eklenti, diğer oyunlara evrimleşecek · ayrıntı ÖNERİ | **İnce zorunlu çekirdek** (`handshake, observe, act, runSkill, interrupt, reset, events`) + isteğe bağlı yetenekler (predicates, knowledge, scenario, record, hafıza çıkarıcıları…). Sözleşme önce Minecraft eklentisinde olgunlaşır, ViZDoom spike'ıyla (S8) sınanır. Genellik metriği: eklenti geliştirme süresi, tekrarlanan kod, kaçış yolları, davranış uyumu ("çekirdek değişikliği ≈ 0" tek başına değil) (research.md §5.2–5.4) |
| 9b | Otonomi | KARAR (Fatih, 2026-10-15) | Otonomi seviyesi bir **seçenek**: `full` (asla sormaz), `approver` (riskli işlerde sorar), `consult` (danışır). Soru botu asla kilitlemez (zaman aşımı + varsayılan). **İletişim tercihi yetkiden ayrıdır:** zaman aşımı yeni yetki vermez; riskli adım atlanır, alternatif seçilir veya görev güvenle sonlanır. Varsayılan: AFK `full`, öğretme `consult`. Ölçüm: `full`'da yanlış varsayım, sonradan düzeltme ve geri alınamaz eylem sayısı (research.md §5.7) |
| 10 | System 1 (L1) | ÖNERİ (inceleme sonrası değişti) | **Acil tehlike L0'da** (olay → eylem ≤100 ms). L1 = olay tetikli taktik seçim + dil-anlamsal noktalar (komut→beceri, anlatım türü, beceri yeniden sıralama, kısır döngü), p95 ≤300 ms. Yeni L1 noktası önce **gölge modda**. `DecisionClient`: teslimde kural + Jev (anahtar var) + 1 yerel aday; eşikler `(soru, sağlayıcı, sürüm, projeksiyon)` başına; sayısal/geometrik hesap kodda. Unsloth–TypeSafe SDK uyumu doğrulanmadı |
| 10b | Model katmanları | ÖNERİ | L0 refleks kodu → L1 karar modeli → L2 frontier LLM → L3 çevrimdışı (etiketleme, fine-tune). Yükseltme merdiveni ve karar noktası haritası: research.md §6 |
| 10c | Soru kayıt defteri | ÖNERİ | Her L1 karar noktası sürümlü bir soru tanımıdır (talimat, kriter, durum projeksiyonu, eşik, yedek); her çağrı loglanır → benchmark + fine-tune verisi |
| 10d | Değer testi | ÖNERİ | Bir L1 noktası, aynı karar için yazılmış L0 kuralını ölçülerek geçemezse L0'da kalır |
| 11 | Kayıt (Minecraft) | ÖNERİ | `minecraft-protocol` proxy'si; vanilla client → proxy → sunucu; paket → anlamlı olay → alt hedef → beceri → taze dünyada doğrulama |
| 11b | Kayıt anlatımı | KARAR (Fatih, 2026-10-15) | Sesli **veya** metin. Metin: oyun içi sohbette `//` önekli notlar (proxy yakalar). Ses: yerel Whisper, zaman damgasıyla olaylara hizalı |
| 11c | Kayıt çıktısı | ÖNERİ | İki artefakt: çalıştırılabilir kod beceri + niyet kartı (ne zaman, girdiler, kurallar, durma, tamamlanma yüklemi). Otonomi seviyesine bağlı: `full`'da soru yok (varsayımlar bildirilir, Kaydet/Güncelle/At otomatik), `consult`'ta zaman aşımlı takip soruları; taze dünyada otomatik doğrulama (research.md §4.3, §4.6) |
| 11d | Oyun hafızası | ÖNERİ | Tek RAG değil: yer kayıtları, kaynak durumu, sandık hafızası, olay günlüğü + RAG, dersler/kararlar (hepsi kapsamda; sıralama §12). Konum/kaynak soruları kodla. Kimlik: `world_instance_id + episode_id + reset nesli` (**seed kimlik değil**) (research.md §7) |
| 11e | Donanım | KARAR (Fatih, 2026-10-15) | `fatih-pc` RTX 5070 Ti 16 GB: L1 karar modeli eğitimi + yerel servis, embedding, Whisper. Fatih gerçek Minecraft client'ını kuracak |
| 11f | Beceri tasarımı | ÖNERİ | 5 seviye (refleks → primitive → temel → bileşik → rutin); her becerinin sözleşmesi (parametre şeması, ön/son koşul yüklemi, yan etki, tipli hata, iptal/devam, risk, süre); yaşam döngüsü taslak → doğrulanmış → güvenilir → emekli; senaryo testleri + regresyon; genel `obtain(item, n)` tarif çözücüsü; elle hazırlanmış başlangıç çekirdeği (research.md §8) |
| 11g | Komut / pipeline | ÖNERİ | Doğal dil, ses ve görsel pipeline aynı **görev grafiğine** (Task IR: skill, sequence, fallback, loop, condition, trigger, guard, budget, report) derlenir. Önce deterministik `#komut` ayrıştırıcı, sonra L1, sonra L2. Geri okuma; onay sadece `consult`'ta ve zaman aşımlı; kalıcı durum; AFK özeti (research.md §9) |
| 11h | Kişilik | ÖNERİ | İsteğe bağlı persona + sınırlı ruh hali + anlatım + günlük + öne çıkan anlar. Oyuncu komutu her zaman öncelikli, "iş modu"nda kapalı. Kayıp sonrası toparlanma ve kısır döngü tespiti kişilikten bağımsız, her zaman açık (research.md §10) |
| 12 | Teslim kapsamı | KARAR (Fatih, 2026-10-15) | **Vizyondaki her şey teslim kapsamında** (ses, editör, approver/consult, kişilik, epizodik RAG, L3 fine-tune, ikinci oyun **Doom teslimden sonraki iş**). İnceleyicilerin takvim riski **sıralamayla** yönetilir: önce ana iddiayı ölçen çekirdek (M0–M5), her taşta ölçüm güncellenir, genişletmeler sonra (research.md §12) |
| 13 | Eylem hakemi | ÖNERİ | Tek eylem sahibi: beceri, L0, L1 ve tetikleyiciler önerir; hakem öncelikle (acil güvenlik > oyuncu komutu > tetikleyici > görev) seçer, kaynak sahipliğini yönetir, kesme onayı bekler, eski işlerin geç sonuçlarını atar, devamdan önce ön koşulları yeniden doğrular (research.md §6.4) |
| 14 | Değerlendirme protokolü | ÖNERİ | Ön kayıt; öğrenme ≠ test seed'leri; testte kütüphane donuk; verilen ve öğrenilen beceriler ayrı; ana kollarda ≥20–30 eşleştirilmiş koşu + McNemar/bootstrap; tek ana hipotez önce; kısa RCON senaryoları ağırlıklı; duvar saati bütçesi (research.md §11.1) |
| 15 | Algı ve yetki | KARAR (görünürlük, Fatih 2026-10-15) + ÖNERİ (yetki) | **İki görünürlük modu:** adil mod (değerlendirme/rapor varsayılanı; sadece görüş hattındaki ve havaya bakan bloklar) + tam bilgi modu (AFK'da seçilebilir); mod her sonuç dosyasına yazılır. Yetki: ajan op değil; senaryo/reset/gerçek durum sadece değerlendiricide (RCON); oyun içi metin talimat değil veri |

| 16 | Ana iddia | KARAR (Fatih, 2026-10-15) | **Oynayarak öğrenme:** öğrenilmiş beceri kütüphanesi, görülmemiş dünyalarda başarıyı düşürmeden süreyi ve LLM çağrısını azaltır. Gösterimden öğrenme ve AFK güvenilirliği destekleyici sonuç (research.md §11) |
| 17 | "Mükemmel" tanımı | KARAR (Fatih, 2026-10-15) | **Kademeli.** Ana: easy + adil mod + görülmemiş seed'lerde elmas kazma, normal zorlukta 3 oyun günü hayatta kalma, 25 görevlik set. Esnek: bilinmeyen dünyada, survival'da, hazır rota olmadan Ender Dragon. Yoldaş davranışı AFK görevleriyle (research.md §11) |
| 18 | Kayıt sırası | KARAR (Fatih, 2026-10-15) | **Aşamalı:** v1 deterministik blueprint + alt hedef makrosu; v2 davranışsal beceriler (tarım, savaş) LLM ile, görülmemiş arazide doğrulanarak. İkisi de kapsamda (research.md §4.6) |
| 19 | Mindcraft | KARAR (Fatih, 2026-10-15) | **Parça ödünç al, üstüne kurma:** Minecraft eklentisine test edilmiş beceriler/dünya yardımcıları, Mineflayer eklenti yamaları, ViaProxy kurulumu, görev JSON formatı. MIT; alınan her dosya kaynak + sürümle kaydedilir. Çekirdek bizim (research.md §5.5) |

**Dış inceleme (2026-10-15):** Opus 5.5 ve GPT-6-Astra tüm tasarımı bağımsız eleştirdi. Ortak bulgular yukarıdaki kararlara işlendi; Fatih'in kararını gerektirenler 2026-10-15'te karara bağlandı (kararlar 5, 12, 15–19; research.md §14.4). Ham raporlar: `docs/reviews/`. Kod aşamasına geçince **ilk iş research.md §14.6 spike'ları (S1–S8)**.

## Mimari (hedef)

Ayrıntı ve diyagram: [docs/research.md §5](docs/research.md). Modüller (henüz kod yok):

Çekirdek / host (`core/`, **Python**, oyundan bağımsız — içinde oyun adı, blok veya eşya adı geçmez):
- `orchestrator` — otonomi motoru: learn / run-task / eval döngüleri, karar günlüğü
- `plugins` — eklenti yükleyici, handshake, yetenek pazarlığı, protokol sürümleme, uyum test kiti
- `planner` (L2) — curriculum, action (beceri kodu yazar), critic (yedek), Haiku → Sonnet kademesi
- `decisions` (L1) — `DecisionClient` + sağlayıcılar (typesafe, unsloth-local, logit-local, nli-local, llm-structured, rules), soru şablonları + kayıt defteri, yükseltme merdiveni
- `arbiter` — tek eylem sahibi: öncelikler, kaynak sahipliği, kesme onayı, eski sonuçları atma
- `monitor` — L0 acil güvenlik refleksleri + olay tetikli L1 taktik kararlar → hakeme öneri
- `training` (L3) — senaryo üretici (eklentinin senaryo kurucusunu kullanır), counterfactual etiketleme, veri seti, S1-Bench
- `skills` — beceri kütüphanesi: sözleşme, yaşam döngüsü, test koşucusu, arama, sürüm, onarım
- `tasks` — görev grafiği (Task IR), `#komut` ayrıştırıcı çatısı, doğal dil/ses derleyici, davranış ağacı çalışma zamanı, tetikleyiciler, kalıcı durum, zamanlama
- `memory` — yer kayıtları, kaynak defteri, depo hafızası, olay günlüğü + RAG, dersler/kararlar; tazelik ve unutma
- `recording` — oyundan bağımsız aşamalar: soyutlama → temizleme → bölütleme → çıkarım → doğrulama
- `persona` — isteğe bağlı kişilik: ruh hali, anlatım, günlük, öne çıkan anlar
- `executor`, `verifier`, `telemetry`, `ui` (CLI + web panosu kabuğu, ses)

Oyun eklentileri (`plugins/<oyun>/`, her biri ayrı süreç, manifest + bileşenler, research.md §5.2):
- `plugins/minecraft` (**TypeScript**) — Mineflayer adaptörü, primitive'ler, `node:vm` sandbox, yüklemler, bilgi sağlayıcı (`minecraft-data` tarif grafiği → `obtain`), sözlük, hafıza çıkarıcıları, senaryo kurucu (`/give /tp /summon /fill`), kayıt proxy'si, başlangıç becerileri, L1 soru paketi, prompt parçaları, `#komut` sözlüğü, prismarine-viewer paneli
- Teslim sonrası: `plugins/doom` (Python, ViZDoom), sonra `plugins/retro`, `plugins/desktop-pixel`

## Kurallar

- **Aşama (2026-10-15'ten itibaren): kod aşaması, GitHub issue/PR akışıyla.** Teslim 2026-11-19. Plan research.md §12.

## Çalışma akışı (GitHub)

Repo: `fthsrbst/minecraft-agent` (private). Kodu agent yazar, **Fatih inceler ve anlar**; amaç aynı zamanda profesyonel akışı öğrenmek.

1. **Her iş bir issue ile başlar.** Şablonlar `.github/ISSUE_TEMPLATE/` altında: görev, spike, hata. Issue'da kapsam, kabul ölçütü ve milestone (Hafta 1–5) olur.
2. **Dal:** `issue-<no>-<kisa-ad>` (örn. `issue-3-sandbox-watchdog`). `main`'e doğrudan commit yok.
3. **Küçük PR'lar.** Bir PR tek bir issue'yu kapatır; ideal boyut birkaç yüz satır. PR açıklaması `.github/pull_request_template.md` formatında; **"Öğrenme notu"** bölümü zorunlu: hangi kavram, neden böyle, nereye bakmalı.
4. **Doğrulama PR'dan önce:** testler, lint, tip kontrolü yerelde geçer; ne çalıştırıldığı ve çıktısı PR'a yazılır. Doğrulanamayan şey açıkça "doğrulanmadı" diye yazılır.
5. **İnceleme:** Fatih PR'ı inceler, soru sorar veya değişiklik ister. Agent yorumlara cevap verir, düzeltmeyi aynı dala ekler.
6. **Merge:** sadece Fatih onayladıktan sonra. Squash merge; commit mesajı emir kipinde, ilk satır ≤ 72 karakter.
7. **Commit ve PR imzası:** commit mesajları `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` ile, PR açıklamaları `🤖 Generated with [Claude Code](https://claude.com/claude-code)` ile biter.
8. **Etiketler:** `type:*` (feature, spike, bug, docs, chore), `area:*` (core, minecraft, l1, l2, memory, skills, tasks, recording, eval, infra), `priority:p0/p1/p2`.
9. Yarım kalan iş hem issue yorumuna hem `docs/backlog.md`'ye yazılır.

- Kod standardı:
  - **Python (çekirdek):** 3.13, `uv` ile ortam, `ruff` (lint + format), `pyright` strict, `pytest`. Modül adları snake_case.
  - **TypeScript (Minecraft eklentisi):** strict, npm, prettier + eslint, kebab-case dosya adları.
  - İngilizce identifier'lar; kullanıcıya görünen metin Türkçe olabilir.
- **Güvenlik**: LLM'in yazdığı kod bu makinede çalışır. Ajanı **asla public bir sunucuya bağlama**; sadece yerel Docker sunucusu.
- **Ölçüm zorunlu**: LLM çağrısı yapan her yeni kod yolu telemetry'den geçmeli (token, maliyet, gecikme). Rapor bunlardan üretilecek.
- **Tekrarlanabilirlik**: deney ve eval koşuları sabit seed + hard reset ile çalışır; seed ve model adı sonuç dosyasına yazılır.
- Sırlar (API anahtarları) sadece `.env`'de; `.env` git'e girmez, `.env.example` güncel tutulur.
- Dış servis çağrılarında timeout + anlamlı hata mesajı zorunlu; hataları yutma.
- Bir beceri/primitive değişince ilgili eval görevlerini yeniden koş; sonucu backlog'a veya notes'a yaz.
- **Çekirdek oyundan bağımsız kalır**: `core/` içinde `minecraft`, `mineflayer`, blok/eşya adı geçmez; oyuna özel her şey eklentide. Çekirdeğe oyun için bir şey eklemek gerekiyorsa bu bir **sözleşme eksiğidir**: eklenti sözleşmesini genel biçimde genişlet (sürüm artır), oyuna özel kodu çekirdeğe koyma.
- **Otonomi kuralı**: kullanıcıya soru soran her akış otonomi seviyesine bağlı olmalı (`full`'da hiç çalışmaz) ve **zaman aşımı + varsayılan cevap** içermeli. Cevap gelene kadar süresiz bekleyen hiçbir akış eklenmez.
- Yeni araştırma tek dosyaya, `docs/research.md`'ye bölüm olarak eklenir (ayrı research dosyası açılmaz).

## Oturum sonu

1. Yarım kalan işi `docs/backlog.md`'ye yaz (format o dosyada).
2. Kalıcı bir gözlem/fikir varsa `docs/notes.md` → "Agent notları"na ekle.
3. Hub: `session_log` + odak değiştiyse `project_update` (proje: `minecraft-agent`).
