# Araştırma: Öğrenen Oyun Ajanı (ilk prototip: Minecraft)

> Son güncelleme: 2026-10-15 · Tek araştırma belgesi; yeni araştırmalar buraya bölüm olarak eklenir.
> Bu belge bir **karar girdisidir**; kesinleşen kararlar `AGENTS.md` → "Kararlar" tablosuna taşınır.

## 0. Özet ve vizyon

**Ne yapıyoruz:** Sadece Minecraft oynayan bir bot değil, **farklı oyunları oynayabilen genel bir bot sistemi**. Sistem oyun oynadıkça ve insanı izledikçe **beceri kütüphanesi** biriktirir. İlk prototip Minecraft oynayacak ve bunu "mükemmel" yapmalı (§11'de ölçülebilir tanımı var).

**Ana fikirler:**

1. **Voyager döngüsü** (§1): müfredat görev önerir → LLM beceri kodu yazar → kod oyunda çalışır → sonuç doğrulanır → beceri kütüphaneye girer.
2. **System 1 / System 2 ayrımı** (§2): yavaş ve akıllı LLM (Claude) planlar ve kod yazar. **Jev** gibi hızlı bir "karar modeli" ise oyun akarken saniyede 5–10 kez küçük kararlar verir. Yol bulma ve nişan almayı ise düz kod yapar.
3. **Record a skill** (§4): oyuncu oyunu oynayarak öğretir (anlatım sesli veya metin); sistem bunu parametreli, otomatik test edilmiş bir beceriye çevirir. Claude ve Codex'in kayıt özellikleri ayrıntılı incelendi.
4. **Model katmanları** (§6): L0 refleks kodu (acil tehlike dahil) → L1 Jev/yerel karar modeli → L2 frontier LLM (Sonnet 5.5 varsayılan, Haiku 5.5 metin işleri; kademe ve Opus ölçülerek) → L3 çevrimdışı öğrenme (veri etiketleme, oyuna özel fine-tune). Her karar, onu yeterince iyi yapan en hızlı katmanda verilir. Jev ile yerel modeller aynı arayüz arkasında ölçülerek karşılaştırılır.
5. **Oyun hafızası** (§7): dünya haritası (ev, portal, köy, maden… konum + durum), kaynak defteri ("bu maden tükendi mi?"), sandık içerikleri, olay günlüğü ve kararlar. Konum ve kaynak soruları kodla sorgulanır; RAG sadece serbest metin geçmiş için.
6. **Beceri tasarımı** (§8): beş seviyeli hiyerarşi, her becerinin sözleşmesi ve testi, genel `obtain(item, n)` çözücüsü, elle hazırlanmış başlangıç kütüphanesi. Hızın asıl kaynağı bu.
7. **Komutlar ve pipeline'lar** (§9): doğal dil, ses veya görsel pipeline → tek bir görev grafiği (koşul, tetikleyici, sınır, bütçe). AFK'dayken "git demir kaz, dolunca boşalt, gece uyu" gibi işler.
8. **Yaratıcılık ve kişilik** (§10): GPT-6 Astra'nın creeper olayından ilham; kayıp sonrası toparlanma, isteğe bağlı persona + ruh hali, günlük, öne çıkan anlar. Aynı ay bir başka deney, GPT-6 Astra + Jev + Mineflayer ile Ender Dragon'u 8 dk 43 sn'de kesti; bu bizim katman mimarimizin dışarıdan bir doğrulaması.

**Genellik nasıl sağlanıyor (§5):** Çekirdek hiçbir oyunu bilmez; **Minecraft bir eklentidir.** Her oyun manifest + bileşenler (adaptör, primitive'ler, yüklemler, bilgi sağlayıcı, sözlük, senaryo kurucu, kayıt yakalayıcı…) sağlayan bir eklentiyle bağlanır. Sıradaki eklentiler ViZDoom (Python), retro emülatör ve piksel tabanlı genel eklenti. Sağlık ölçütü: yeni eklentide çekirdek değişikliği ≈ 0.

**Otonomi (§5.7):** Otonomi seviyesi bir **seçenektir**: `full` (asla sormaz), `approver` (sadece riskli işlerde sorar), `consult` (danışır). Hangi seviyede olursa olsun soru botu kilitlemez; her sorunun zaman aşımı ve varsayılan cevabı (botun kendi kararı) vardır. AFK için varsayılan `full`.

**Dış inceleme (§14):** Opus 5.5 ve GPT-6-Astra tasarımı bağımsız olarak eleştirdi. Ortak bulgular uygulandı: ayrı süreçte izole beceri yürütme, acil tehlikenin L0'a alınması, tek eylem sahibi, bağımsız doğrulama yüklemleri, eğitim/test ayrımı ve güçlü istatistik, ince eklenti çekirdeği. Senin kararınla çelişen öneriler §14.4'te karar bekliyor.

**Bilgi düzeltmesi — "Jev Doom'u bitirdi" mi?** Hayır, elimizdeki kaynaklar bunu desteklemiyor (§2.3):
- TypeSafe'in kendi demosu bir **hız gösterisi**: oyun durumunu metin olarak verip saniyede ~10 karar alıyor. Kaynaklara göre senaryolu bir bot onu yenerdi.
- Topluluk reposu `jev-plays-doom` tek bir arenada (`defend_the_center`) elle yazılmış nişan botuyla **aynı** ortalama skoru aldı (6.55 öldürme).
- Blocks.ai'nin açık replikası Freedoom MAP01'de 300 kararda 5 öldürme ve 8 eşya topladı, ölmedi. Bölümü bitirdiği raporlanmadı.

Asıl ders şu: "model küçük kararları **hızlı** verir, gerisini kod yapar."

---

## 1. Minecraft ajanları — Voyager ve rakipleri

### 1.1 İki aile

| Aile | Gözlem | Eylem | Örnekler | Bizim için |
|---|---|---|---|---|
| **Kod/API tabanlı** | Oyun API'sinden metin: envanter, bloklar, konum… | LLM, bot API'sini çağıran **kod** yazar | Voyager, Mindcraft, ODYSSEY, MindForge, Project Sid | ✅ Minecraft prototipi |
| **Piksel/klavye-fare (VLA)** | Ekran görüntüsü | Eğitilmiş politika, düşük seviye tuşlar | VPT, STEVE-1, JARVIS-1, Optimus-1/2/3, Lumine, NitroGen, Game-TARS | ⚠️ API'si olmayan oyunlar için yedek yol (§3) |

Mineflayer: Minecraft sunucusuna **gerçek oyuncu gibi** bağlanan Node.js botu. Yol bulma (`mineflayer-pathfinder`), kazma, craft, envanter, savaş (`mineflayer-pvp`), ok (`minecrafthawkeye`), blok toplama (`mineflayer-collectblock`) API'leri var. LLM'in işi bu API'yi doğru sırayla ve doğru koşullarla çağıran programlar yazmak.

### 1.2 Voyager — kaynak koddan çıkarılan mimari

Kaynak: Wang ve ark. 2023 ([arXiv 2305.16291](https://arxiv.org/abs/2305.16291), NeurIPS 2023), kod: [MineDojo/Voyager](https://github.com/MineDojo/Voyager) (MIT, bakımsız).

| Bileşen | Dosya | Görev |
|---|---|---|
| CurriculumAgent | `voyager/agents/curriculum.py` | Sonraki görevi önerir ("Mine 3 iron_ore"). Önce kendine sorular sorar, cevapları `qa_cache.json`'da önbellekler. |
| ActionAgent | `voyager/agents/action.py` | `async function xxx(bot)` JavaScript fonksiyonu yazar |
| CriticAgent | `voyager/agents/critic.py` | Son durumdan `{reasoning, success, critique}` JSON'u üretir |
| SkillManager | `voyager/agents/skill.py` | Başarılı programı LLM'e açıklatır, açıklamayı Chroma'ya embed eder, arama top-k=5 |
| VoyagerEnv | `voyager/env/bridge.py` + `env/mineflayer/index.js` | Python ↔ Node Express köprüsü (`/start`, `/step`). Kod çıplak `eval` ile çalışır. |

**Döngü:** Toplam en fazla 160 iterasyon, her görev için en fazla 4 deneme. Her denemede LLM'e sadece `[system, human]` iki mesaj gider: geçmiş yerine "son kod + hata + eleştiri" human mesajına gömülür, böylece bağlam boyu sabit kalır. 15 görev tamamlanınca dünya peaceful'dan easy'ye geçer.

**Diğer önemli detaylar:**
- Başarısız inşa denemelerinde yerleştirilen blokları geri toplar (`reset_placed_if_failed`).
- Sandık içeriklerini hafızada tutar.

**Gözlem:** son kod, hata, sohbet logu, biyom, saat, yakın bloklar, yakın varlıklar, can, açlık, konum, ekipman, envanter (xx/36), sandıklar, görev, bağlam, eleştiri.

**Primitive'ler:** `mineBlock`, `craftItem`, `smeltItem`, `placeItem`, `killMob`, `exploreUntil`, `useChest`, `shoot`, `waitForMobRemoved`. Gerçek implementasyon (`control_primitives/`) ile LLM'e gösterilen sade sürüm (`control_primitives_context/`) ayrı dosyalarda — iyi bir fikir.

**Prompt kuralları (`prompts/action_template.txt`):**
- Primitive'leri kullan, `bot.dig` gibi ham çağrılar yapma.
- Genel ve yeniden kullanılabilir yaz; envantere güvenme, eksik varsa önce topla.
- Sonsuz döngü veya özyineleme yazma; `bot.on` ile olay dinleyici kaydetme.
- `findBlocks` için maxDistance her zaman 32 ("Do not cheat").
- Yanıt formatı: `Explain → Plan → Code`.

**Müfredat kuralı:** Görsel doğrulama gerektiren görevler (inşa, yerleştirme, ekim, takas) önerilmez.

**Sonuçlar:**
- Önceki SOTA'ya göre 3.3× daha fazla benzersiz eşya.
- Teknoloji ağacı kilometre taşlarına 15.3× daha hızlı ulaşım.
- Ablasyonda müfredat, beceri kütüphanesi ve öz-doğrulamanın üçü de kritik çıktı.

**Zaafları:**
- GPT-4 maliyeti: ODYSSEY yazarlarına göre deney başına "binlerce dolar".
- İmkânsız görev önerebiliyor ("copper sword").
- Primitive listesinde olmayan fonksiyonlar uydurabiliyor.
- Kodu sandbox'sız `eval` ile çalıştırıyor.
- Başarıya karar veren tamamen LLM.
- Başarısızlıktan kalıcı ders çıkarmıyor.
- **Gerçek zamanlı tepki yok**: kod çalışırken tehlikeye tepki veremiyor, deneyler çoğunlukla peaceful modda.
- MC 1.19 + Azure login'e sabit.

### 1.3 Rakipler (kod/API tabanlı)

| Sistem | Öne çıkan fikir | Ders |
|---|---|---|
| **Mindcraft** + MineCollab ([repo](https://github.com/mindcraft-bots/mindcraft), [arXiv 2504.17950](https://arxiv.org/abs/2504.17950)) | Saf Node, ~47 parametreli komut (`!collectBlocks("oak_log",1)`) + isteğe bağlı kod modu. Çok sağlayıcı, çok ajan. ~5.9k⭐, aktif, MC ≤1.21.11. | En olgun açık kaynak. "Komut mu, kod mu" ikilemi. Ajanlardan ayrıntılı plan iletişimi istendiğinde performansta %15'e varan düşüş. |
| **ODYSSEY** ([arXiv 2407.15325](https://arxiv.org/abs/2407.15325)) | 40 primitive + 183 bileşik hazır beceri. Wiki ile fine-tune edilmiş LLaMA-3. Planner–actor–critic yapısı. | Güçlü bir **başlangıç kütüphanesi** ver; ucuz açık model kullan. |
| **MindForge** ([arXiv 2411.12977](https://arxiv.org/abs/2411.12977)) | Voyager + theory of mind + ajanlar arası iletişim | Açık 7–8B modeller Voyager'da temel görevlerde bile zorlanıyor. |
| **MineEvolve** ([arXiv 2603.13131](https://arxiv.org/abs/2603.13131), 2026) | Tipli geri bildirim (envanter farkı, hata türü, durma). Başarıdan beceri, başarısızlıktan **çare (remedy)** çıkarıyor. | Başarısızlıktan öğrenme. |
| **Evolving Programmatic Skill Networks** ([arXiv 2601.03509](https://arxiv.org/abs/2601.03509), 2026) | Beceriler birbirini çağıran bir program ağı. Hata yeri tespiti, olgunluğa göre güncelleme kapısı, geri almayla doğrulanan refactor. | Kütüphane büyüdükçe **onarım ve sadeleştirme** gerekir. |
| **Project Sid / PIANO** ([arXiv 2411.00114](https://arxiv.org/abs/2411.00114)) | 1000+ ajan; eşzamanlı modüller (hafıza, eylem, sosyal, konuşma) ve bir karar darboğazı | Gerçek zamanlılık için **paralel modüler** mimari. |
| **GITM** ([arXiv 2305.17144](https://arxiv.org/abs/2305.17144)) | Hedef → alt hedef → yapılandırılmış eylem; GPU'suz | Hiyerarşik ayrıştırma. ObtainDiamond'da %67.5. |
| **minecraft-mcp-server** ([repo](https://github.com/yuniko-software/minecraft-mcp-server)) | Mineflayer'ı MCP araçları olarak Claude'a açıyor | Öğrenme yok; ama MCP ile etkileşimli demo için referans. |
| **Player2NPC / PlayerEngine** ([Modrinth](https://modrinth.com/mod/player2npc)) | Ticari "AI yoldaş" Fabric modu: LLM komut üretiyor, motor yürütüyor | Ürün karşılığı; öğrenme yok. |

Piksel tabanlı Minecraft ajanları:
- **JARVIS-1** ([arXiv 2311.05997](https://arxiv.org/abs/2311.05997)): multimodal hafıza, ObtainDiamondPickaxe %12.5.
- **Optimus-1** ([arXiv 2408.03615](https://arxiv.org/abs/2408.03615)): bilgi grafiği + deneyim havuzu.
- **VPT**, **STEVE-1**.

### 1.4 Benchmark'lar

- **MCU**: uzun ufuklu görevler.
- **MineCollab**: görev JSON formatı (`goal`, `initial_inventory`, `target`, `timeout`, `blocked_actions`) → **bizim test şablonumuz**.
- **MineNPC-Task** ([arXiv 2601.05215](https://arxiv.org/abs/2601.05215)): makinece doğrulanabilir validator'lar, oyun dışı kısayollar yasak. GPT-4o'nun tekrarlayan hataları kod çalıştırma, envanter, referans ve navigasyon alanlarında.
- **MineExplorer** ([arXiv 2605.30931](https://arxiv.org/abs/2605.30931), EMNLP 2026): gizli ön koşullar uzadıkça sert düşüş; büyük model veya thinking modu tutarlı fayda sağlamıyor.
- **PillagerBench** ([arXiv 2509.06235](https://arxiv.org/abs/2509.06235)): rekabetçi takım oyunları.

### 1.5 Beceri kütüphanesi literatüründen dersler (2026)

- **Skill drift** ([arXiv 2605.10990](https://arxiv.org/abs/2605.10990)): beceriler, bağlı oldukları API veya sürüm değişince **sessizce bozulur**. Her beceriden bir "ortam sözleşmesi" çıkarıp proaktif doğrulamak gerekir.
- **SkillsBench** ([arXiv 2602.12670](https://arxiv.org/abs/2602.12670)) ve "Skills in the wild" ([arXiv 2604.04323](https://arxiv.org/abs/2604.04323)): becerilerin faydası kırılgan. Kütüphanenin katkısı **ablasyonla** kanıtlanmalı.

---

## 2. Jev ve System One modelleri

### 2.1 Jev nedir?

**Jev**, TypeSafe AI'ın ilk "System One" modeli. Şirketin CEO'su Diogo Almeida (eski OpenAI araştırmacısı, RLHF'in ortak mucitlerinden); şirket 40 milyon dolar yatırım almış ([The Register](https://www.theregister.com/ai-and-ml/2026/09/16/typesafe-ai-debuts-model-for-machines-that-plays-doom/5296711)).

**Metin üretmez.** Program durumunu (JSON veya metin) alır ve **tipli, olasılıklı kararlar** döndürür. Tüm sorular tek bir paralel geçişte cevaplanır.

| Primitive | Ne döner | Oyunda örnek |
|---|---|---|
| **Choice** | Tanımlı seçeneklerden biri + her seçeneğin olasılığı + güven skoru | "Şimdi ne yapmalı: savaş / kaç / ye / devam et" |
| **Noul** | "Evet" olasılığı | "Bir yaratık 1 saniye içinde bana zarar verebilecek kadar yakın mı?" |
| **Score** | Tanımlı seviyeler üzerinde konum | "Bu görev şu anki envanterle ne kadar zor?" |
| **Box** (Jev 1.14, deneysel) | Görüntüde hedefin kutusu | Ekranda düşmanı veya butonu bulma |

**Rakamlar:**
- **Gecikme:** 70–500 ms (şirket iddiası, "LLM'lerden 40–200× hızlı"). Topluluk ölçümü: Doom'da 212 ms ortalama, 2,642 çağrı.
- **Fiyat:** $0.042 / 1M girdi token'ı, çıktı ücretsiz ([models](https://docs.typesafe.ai/models.md)).
- **Bağlam:** istek başına 64k, soru başına 32k token (özel başlıkla 262k; daha yavaş ve daha az doğru).
- **Sürümler:** `jev-1.13.0` kararlı, `jev-1.14.0` 2026-10-14'ten beri önizleme.
- **Görüntü:** PNG/JPEG, kenar başına 256–1568 px, `TypeSafe-Danger-Zone-Images: true` başlığıyla. "Production-ready değil" etiketli ([images](https://docs.typesafe.ai/images.md)).
- **Erişim:** Sadece barındırılan API, erken erişim. İndirilecek ağırlık yok. JS ve Python SDK'ları var.

### 2.2 Zayıf yanları (resmî "jaggedness" sayfası, [jev-1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md))

- **Hesap makinesi değil:** sayma, aritmetik ve hassas sayısal karşılaştırma güvenilmez → **mesafe, açı ve sayıları kod hesaplamalı**.
- **Uzun ve alakasız durum** doğruluğu düşürüyor (context rot) → modele sadece ilgili alanları ver.
- **Seçenek sırası** cevabı etkileyebiliyor (ilk seçeneğe eğilim) → sırayı karıştırıp tutarlılığı test et.
- Kelimesi kelimesine okuma, çok adımlı dolaylı akıl yürütme ve durum içine gömülü kötü niyetli içerik de zayıf noktalar.
- Tipli çıktı yalnızca **arayüzü** garanti eder, **doğruluğu değil**. Doğruluk her kullanım alanında ayrıca ölçülmeli.

### 2.3 Doom deneyleri — gerçekte ne oldu?

| Deney | Kurulum | Sonuç |
|---|---|---|
| TypeSafe resmî demo | Yapılandırılmış durum (can, düşman konumları, mesafe), saniyede ~10 karar, ~$7/saat ([LumaDock](https://lumadock.com/blog/what-is-jev-typesafe), [Medium](https://medium.com/@creativeaininja/typesafes-jev-makes-ai-decisions-fast-enough-to-play-doom-68fdcce1159a)) | Hız gösterisi. Senaryolu bot onu yenerdi; LLM'lerin 3–30 sn'lik çağrılarıyla imkânsız olan gerçek zamanlı döngüyü mümkün kılıyor. |
| [jev-plays-doom](https://github.com/tirukovelamanoj/jev-plays-doom) | ViZDoom; `describe()` düşmanların açı ve mesafesini **kodda** hesaplıyor. Tek istekte iki soru: `action` (Choice: ATTACK/TURN_LEFT/TURN_RIGHT) ve `in_danger` (Noul). 4 tick'te bir karar (~8.75 Hz). Güven < 0.5 ise elle yazılmış beyne devrediyor. | `defend_the_center`, 20 epizot: rastgele 0.75, elle nişan 6.55, Jev 6.55 öldürme. **Prompt ifadesi kritik**: "rule" kriteri 6.20, "intent" kriteri −0.60 (hiç ateş etmedi, sürekli döndü). |
| [Blocks.ai açık replika](https://blocks.ai/blog/jev-open-model-doom) | Gemma 4 12B **base** model. Tek ileri geçiş, A–Z harflerinin logit'leri üzerinde softmax → uydurma etiket imkânsız. Prefix KV-cache. M4 Mac'te medyan 113 ms. | Üç senaryo + Freedoom MAP01: 300 kararda 5 öldürme, 8 eşya, ölüm yok. **Navigasyon BFS koduna devredildi**: model her tick yön seçince salınıyordu; BFS ile takılmalar ~33'ten 3'e düştü. Faz seçimini (savaş/sıkıştı/gez) motor verisi yapıyor. |

### 2.4 Bizim için çıkarımlar

1. **Üç hızlı katman** gerekiyor: (a) **refleks kodu** 0 ms — yol bulma, nişan, mesafe; (b) **System 1 / Jev** ~100–300 ms — bağlamsal küçük kararlar; (c) **System 2 / LLM** saniyeler — plan, kod, müfredat, kayıttan beceri çıkarma.
2. Jev'in Minecraft'taki yeri **beceriyi yazmak değil**, beceri çalışırken **izlemek ve yönlendirmek**:
   - **Tehlike monitörü:** ~5 Hz Noul + Choice (devam / kaç / savaş / ye / sığın). Voyager'ın "peaceful'da kalma" zaafını kapatır.
   - **Beceri seçimi ve sıralama:** TypeSafe'in [skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion.md) tarifi 182 beceride yanlış yüklemeyi %16.8'den %7.3'e indirdi (iki çağrı toplam < 1 sn). Embedding ile ön eleme + Jev ile yeniden sıralama.
   - **Görev fizibilitesi ve yenilik skoru** (Score) — müfredata yardımcı.
   - **Bulanık doğrulama** (Noul) — deterministik kontrolün yetmediği yerlerde, LLM critic'ten önce.
   - **Güven kapılı yönlendirme:** düşük güvende Claude'a veya elle yazılmış kurala devret.
3. **Maliyet tahmini:** 2k token durum × 5 Hz × 3600 sn ≈ 36M token/saat ≈ **$1.5/saat**. TypeSafe'in Doom demosu ~$7/saat.
4. **Bağımlılık riski:** Jev kapalı bir servis (API anahtarı var). Bu yüzden `DecisionClient` arayüzü arkasına konur; yerel karar modelleri aynı arayüzle karşılaştırılır (§6.5–6.7).

### 2.5 Jev + GPT-6 Astra + Mineflayer: Ender Dragon 8 dk 43 sn (2026-09-20)

Ronak Malde'nin deneyi ([ASCII.jp](https://ascii.jp/en/elem/000/004/436/4436545/)):
- **İş bölümü:** GPT-6 Astra yüksek seviye planı yapıyor (şimdi ne başarılmalı, nereye gidilmeli). Jev, konum + envanter + çevre + Astra'nın hedefini alıp aday eylemlerden birini seçiyor (yürü, kaz, al, craft, saldır). Mineflayer yürütüyor.
- **Paralellik:** Astra arka planda planlarken Jev seçmeye devam ediyor, oyun durmuyor.
- **Sayılar:** 35 Astra çağrısı (~$0.96), 131 Jev çağrısı (~$0.01).
- **Kurulum:** MC 1.16.5 (vanilla sunucu), peaceful, sabit seed; End portalı önceden doğrulanmış koordinatta; seed'de köy ve 21 obsidyenli 3 sandık hazır; rota Nether üzerinden, blaze rod gerekmiyor; ejderha yatak patlatmayla kesildi.
- **Repo:** [rmalde/minecraft-agent](https://github.com/rmalde/minecraft-agent) ("Astra planner and JEV controller"). Jev `typesafe/jev-1.13` ile çağrılıyor; çağrı sıklığı belgelenmemiş (131 karar / 523 sn ≈ 0.25 Hz). Ejderha başının konumu sunucuya eklenen salt-okur bir **sensörle** (`DragonObserver.java`) okunuyor. Tek doğrulanmış koşu.
- **Bizim için anlamı:** L2 planlayıcı + L1 aday eylem seçici + L0 yürütücü **entegrasyonunun** çalışabildiğini gösteriyor. Öğrenmeyi veya L1'in nedensel katkısını **göstermiyor** (inceleme, §14). L1'in burada saniyede birkaç kez değil, ~0.25 Hz ve olay tetikli çalıştığına dikkat. Fark bizde: bilinmeyen dünya, zorluk, öğrenme.

---

## 3. Genel oyun oynayan ajanlar (tüm oyunlar hedefi için)

| Sistem | Girdi → çıktı | Öne çıkan sonuç | Bizim için |
|---|---|---|---|
| **SIMA 2** (DeepMind, [arXiv 2512.04797](https://arxiv.org/abs/2512.04797), 2025-11) | Piksel + dil → klavye/fare; Gemini tabanlı | Birçok 3D oyunda insana yaklaşıyor. Genel görev tamamlama oranı SIMA 1 %31 → SIMA 2 %65 (Minecraft'a özgü değil; yeni oyunlarda oran çok daha düşük). Yeni ortamda **kendi görevini üretip** ödül modeliyle kendini geliştiriyor. | Kendi kendine müfredat + ödül modeli fikri; ölçeği bizim kapsamımızın çok ötesinde. |
| **Cradle** (BAAI, [arXiv 2403.03186](https://arxiv.org/abs/2403.03186)) | Ekran görüntüsü → klavye/fare **kodu**; API kullanmıyor | RDR2'de 40 dk'lık ana görevleri bitirdi; Stardew Valley, Cities: Skylines, Chrome… | **En yakın genel mimari**: 6 modül (bilgi toplama, öz-yansıtma, görev çıkarımı, **beceri kürasyonu**, eylem planlama, hafıza). "API yoksa" yolumuz için şablon. |
| **Lumine** (ByteDance Seed, [arXiv 2511.08892](https://arxiv.org/abs/2511.08892)) | VLM, birkaç fps kare → yüksek frekanslı klavye/fare; sadece gerektiğinde düşünüyor | Genshin Impact'te 5 saatlik ana hikâyeyi insan hızında bitirdi. Eğitimsiz olarak Wuthering Waves ve Honkai: Star Rail'e transfer etti. | "Sadece gerektiğinde düşün" = bizim S1/S2 ayrımı. Eğitim maliyeti bize uygun değil. |
| **NitroGen** (NVIDIA, [arXiv 2601.02427](https://arxiv.org/abs/2601.02427), CVPR 2026) | RGB → gamepad; 1000+ oyunun 40k saat videosundan, aksiyonlar videodan otomatik çıkarılmış | Yeni oyunda sıfırdan eğitime göre %52'ye kadar göreli iyileşme. **Ağırlıklar açık**, Windows oyunları için çıkarım sunucusu var. | Gamepad oyunları için hazır **refleks politikası** adayı (RTS/MOBA'da zayıf). |
| **Game-TARS** (ByteDance, [arXiv 2510.23691](https://arxiv.org/abs/2510.23691)) | Tek, insan benzeri klavye/fare eylem uzayı; 500B token ön eğitim | Açık dünya Minecraft'ta önceki SOTA'nın ~2×'i; FPS'te GPT-5/Claude-4'ü geçiyor (yazarların iddiası). | Birleşik eylem uzayı fikri. |
| **SpeedrunBench** (Patronus, [arXiv 2610.08076](https://arxiv.org/abs/2610.08076), 2026-10) | Ekran görüntüsü (online) veya aksiyon izini düzenleme (offline); 9 oyun | Pokémon Blue'da ilk rozete sadece üç model ulaştı (Claude Opus 5 ~160K kare; insan rekoru ~40K). Hiçbir model dünya rekoruna yetişemedi. | Frontier LLM'ler pikselden gerçek zamanlı oynamada hâlâ yavaş → **durum API'si olan oyunlar öncelikli**. |
| Diğer benchmark'lar | lmgame-Bench (ICLR 2026), VideoGameBench, BALROG, PokeGym, Orak | — | İkinci adaptör seçiminde referans. |

**Sonuç — üç entegrasyon seviyesi:**

| Seviye | Oyuna nasıl bağlanılır | Örnek | Ajanın gücü |
|---|---|---|---|
| **A — Durum API'si** | Oyunun kendi API'si / bot kütüphanesi / RAM okuma | Minecraft (Mineflayer), Doom (ViZDoom), Game Boy/NES (PyBoy, stable-retro), Factorio (mod API), tarayıcı oyunları (DOM) | En yüksek: kesin durum, kesin doğrulama, kod beceriler |
| **B — Mod/hook** | Oyun modu, eklenti, bellek okuma | Stardew (SMAPI), Unity oyunları (BepInEx) | Yüksek, oyuna özel iş gerekir |
| **C — Sadece piksel + girdi** | Ekran görüntüsü + klavye/fare/gamepad | Herhangi bir oyun (Cradle/Lumine yolu) | En düşük; algı VLM veya Jev görüntü/Box ile, refleks politikası olarak NitroGen |

**Strateji:** Çekirdek üç seviyeyi de destekleyecek şekilde tasarlanır. Ama **önce A seviyesinde mükemmelleşir** (Minecraft); ikinci adaptör de A seviyesi olur (ViZDoom veya bir emülatör oyunu). C seviyesi sonraki aşamadır.

---

## 4. Record a skill — gösterimden beceri öğrenme

Hedef: **oyuncu oyunu oynayarak bota öğretebilsin.** Anlatım **sesli veya metin** olabilir (KARAR, Fatih 2026-10-15).

### 4.1 Claude "Record a skill" (Anthropic, Cowork) — ayrıntılı inceleme

Resmî kaynak: [Claude yardım merkezi](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills). Diğer satırlar basın ve uygulamalı rehberlerden.

| Konu | Bilinen |
|---|---|
| Çıkış | 2026-07-21, Claude Desktop → **Cowork**. Pro / Max / Team planları. **Sadece Mac'te Cowork** (resmî); sohbette, Windows'ta, Free ve Enterprise'da yok. |
| Başlatma | Cowork'te **"+" → Record a skill**, veya **Customize → Skills → Add → Record your screen**. İlk seferde ekran kaydı ve erişilebilirlik izni istenir. Mikrofon seçilir → **Start recording** → iş yapılırken anlatılır → **Done**. |
| Ne kaydediliyor | Ekran etkinliği, tıklamalar, yazılanlar, **ses (anlatım)**. Ekranda görünen ve söylenen **her şey** yakalanıyor. |
| Saklama | Video ve ses Claude kaydı inceledikten sonra **saklanmıyor**; bir dizi ekran görüntüsü görevin "Recorded demonstration" adımında tutuluyor, görev silinince onlar da siliniyor (resmî). |
| Süre sınırı | Kayıt başı **~10 dk**, son dakikada geri sayım; sıfıra inince kayıt durur ve Claude'a gönderilir (resmî). |
| Kayıt sonrası | 1) Bir uygulamalı rehbere göre Claude, anlatımın boş bıraktığı noktalar için **takip soruları** soruyor (örn. "sonuçlar nereye gitmeli?"); **resmî sayfa bunu anlatmıyor**. 2) **Yeni beceri** önerirse *Save / Dismiss*, **mevcut bir beceriyi güncelleme** önerirse *Update / Dismiss* çıkıyor. 3) **Content** açılıp etkinleşme koşulları, öncelikler, hariç tutmalar ve çıktı yapısı kontrol ediliyor. |
| Çıktı | Skills kütüphanesine bir Skill (klasör + `SKILL.md`). İç format Anthropic tarafından yayımlanmadı; kullanıcı raporlarına göre etkinleşme koşulları, öncelikler, hariç tutmalar, çıktı yapısı içeriyor. |
| Tekrar | Beceri, ilgili istek geldiğinde yükleniyor veya zamanlanmış görev olarak çalışıyor. Yürütmeyi model **yorumlayarak** yapıyor (koordinat tekrarı değil). |
| Önerilen kullanım | Her beceri tek iş akışı. **Hariç tutmaları ve nedenini anlat.** Kaydetmeden önce Content'i oku. Yeni girdilerle test et. Şifre ve gizli veri kaydetme. |

**Gözlemlenen sorunlar** ([remio](https://www.remio.ai/post/claude-cowork-skill-recording-turns-demonstrations-into-reusable-workflows-but-t), [leadwithai](https://www.leadwithai.co/article/record-a-skill-claude-cowork)):
- **Tek örnekten aşırı genelleme**: tesadüfi ayrıntı kural sanılabiliyor.
- **Gösterimdeki hatalar da öğreniliyor**: "gizli hataları da iyi muhakeme kadar verimli kopyalar".
- Anlatımla alakasız konuşmanın nasıl ayrıldığı açıklanmamış.
- Uzmanlar kuralları söylemeden uyguluyor (örtük bilgi).
- Aynı tıklamanın arkasında farklı niyetler olabiliyor.
- Yorumlayan yürütme esnek ama öngörülemez.
- Arayüz değişince beceri bozuluyor.
- Hata çıkınca sorumluyu (gösterim mi, yorum mu, model mi) bulmak zor.
- Ana ders: **kayıt beceri üretmeyi kolaylaştırıyor ama doğrulamayı zorlaştırıyor.**

### 4.2 OpenAI Codex / ChatGPT "Record & Replay" — ayrıntılı inceleme

Kaynak: [resmî doküman](https://learn.chatgpt.com/docs/extend/record-and-replay) + uygulamalı denemeler.

| Konu | Bilinen |
|---|---|
| Çıkış | Haziran 2026 (ikincil kaynaklara göre 18 Haziran). **Sadece macOS.** Computer Use açık olmalı. İlk aşamada AB, İngiltere ve İsviçre hariç (ikincil). Kurumsal `requirements.toml` içinde `[features].computer_use = false` ise o da kapanıyor. |
| Başlatma | ChatGPT (Work modu) veya Codex → **Plugins** → **"+" → Record a skill** → önerilen prompt'u gözden geçir, **bağlam ekle** → kayıt iznini onayla → iş akışını yap → menü çubuğundan veya overlay'den durdur ya da sohbete "bitti" yaz. |
| Ne kaydediliyor | "İş akışını öğrenmek için gereken **eylemler ve pencere içeriği**." Durdurulana kadar sürüyor. Ses ve tuş kaydı belgelenmemiş. Bir kaynak 30 dk sınır diyor (doğrulanmadı). |
| Çıktı | `SKILL.md` (+ isteğe bağlı destek dosyaları), varsayılan konum `~/.codex/skills/<ad>`. Becerinin içeriği: **ne zaman kullanılır, hangi girdileri ister, hangi adımları izler, sonucu nasıl doğrular.** Kayıttan sonra sohbetle iyileştirilebiliyor. |
| Örnek ([azukiazusa](https://azukiazusa.dev/en/blog/workflow-to-reusable-skill/)) | Mesai girişi becerisinin bölümleri: *Collect Inputs* (sadece eksik/belirsiz değerleri sor) → *Open app* (tarayıcı otomasyonu varsa onu, yoksa Computer Use) → *Enter Rows* (7 adımlı satır prosedürü) → *Verify* (kaydedilen satırları ve toplamı kontrol et) → *Safety* (ilgisiz kayıtlara dokunma). **Kayıttaki değerler varsayılan değil örnek** sayılıyor; hedefler koordinatla değil **erişilebilir etiket ve rolle** tarif ediliyor; doğrulama başarısızsa tekrar denemeden **dur** (mükerrer kayıt önlemi). |
| Tekrar | Yeni sohbette beceriyi iste, bu sefer farklı olan değerleri ver. Mevcut araçlarla (Computer Use, tarayıcı, eklentiler) yürütülüyor. |
| Resmî ipuçları | Gösterimi kısa ve eksiksiz tut. **Kayıttan önce hedefi ve değişebilecek girdileri söyle.** Gerçekçi ama gizli olmayan veri kullan. Kayıttan sonra **gizli tercihleri** (adlandırma kuralları, varsayılanlar, karar noktaları) ekle. İş bitince durdur, ilgisiz temizliği kaydetme. |

**Denetim kontrol listesi** ([chatgptaihub](https://chatgptaihub.com/audit-repair-codex-record-replay-skill)). Gösterimden gelen beceride sık görülen 10 hata:
1. Kayıttaki değerin girdi yerine kullanılması.
2. Gizli tercihler.
3. Çok geniş kapsam.
4. Arayüz kayması.
5. Tesadüfi (gereksiz) eylemler.
6. Ekrandaki metnin talimat sanılması.
7. Doğrulanmamış başarı.
8. Ortam ve izin eksikleri.
9. Önceden var olan sonucun yeni sonuç sanılması.
10. Durma koşullarının olmaması.

Önerilen çözüm: her değeri **zorunlu girdi / sabit sınır / kayıt gözlemi / çözülmemiş varsayım** olarak sınıflamak.

### 4.3 İki ürünün karşılaştırması ve bize dersler

| | Claude Record a skill | Codex Record & Replay | **Bizim oyun versiyonumuz** |
|---|---|---|---|
| Girdi | Ekran + tık + tuş + **ses** | Eylemler + pencere içeriği | **Oyun olayları (kesin)** + durum anlık görüntüleri + **ses veya metin anlatım** |
| Kayıt öncesi | — | Hedef + değişken girdiler sorulur | `consult`'ta sorulabilir (zaman aşımlı); `full`'da sorulmaz, bot kayıttan çıkarır |
| Kayıt sonrası | **Takip soruları**, Save/Update/Dismiss | Sohbetle iyileştirme | Otonomi seviyesine bağlı (§5.7): `consult`'ta zaman aşımlı takip soruları + öneri; `full`'da soru yok, varsayımlarını bildirir ve Kaydet/Güncelle/At kararını doğrulama skoruyla kendisi verir |
| Çıktı | SKILL.md (yorumlanan talimat) | SKILL.md (ne zaman / girdiler / adımlar / doğrulama) | **İki artefakt**: (1) çalıştırılabilir **kod beceri**, (2) **niyet kartı** (ne zaman, girdiler, kurallar, durma koşulları, tamamlanma yüklemi) |
| Yürütme | LLM yorumlar (esnek, öngörülemez) | LLM + Computer Use yorumlar | **Kod deterministik çalışır**, S1 izler, bozulursa S2 niyet kartından onarır |
| Doğrulama | Kullanıcı elle test eder | Kullanıcı ilk tekrarları denetler | **Otomatik**: taze dünyada + farklı parametrelerle (jitter) tekrar, başarı yüklemiyle ölçüm |
| Genelleme | Tek örnek | Tek örnek | **1–3 gösterim**; gösterimler arasındaki farklar parametreye dönüşür |

**Alacaklarımız** (otonomi seviyesine göre uyarlanır, §5.7):
1. **Anlatım mantığı taşır.** Sadece eylem kaydı yetmez; "neden" ve "ne zaman yapma" cümleleri beceriye kural olarak girer.
2. **Niyet beyanı (isteğe bağlı, sorulmaz):** kullanıcı kayda başlarken "ne öğrettiğini, hangi değerlerin değişebileceğini" kendiliğinden söyleyebilir; söylemezse bot çıkarır.
3. **Boşlukları soru sormadan doldurma:** Claude'un takip soruları yerine bot boşlukları hafıza, benzer beceriler ve kayıt kanıtıyla kendisi doldurur; varsayımları niyet kartına yazar ve bildirir.
4. **Kayıttaki değerler örnektir, varsayılan değildir.**
5. **Hedefleri anlamsal tarif et:** "en yakın meşe ağacı", koordinat değil.
6. **Doğrulama başarısızsa dur, körlemesine tekrar etme.**
7. **Yeni beceri mi, var olanın güncellemesi mi** kararı (bot verir).
8. **Değer sınıflandırması** (Codex denetim listesinden).

**İki üründe de olmayan, bizim ekleyeceklerimiz:**
- **Kesin olay akışı.** Oyunda pikselden tahmin yerine protokolden gelen kesin olaylar var. Bu, iki ürünün en zayıf halkasını (algı) ortadan kaldırıyor.
- **Otomatik test ve onarım döngüsü.** Work2Skill'in üretim hattında bulunmayan kabul/onarım kapısı.
- **Hata ve sapma ayıklama.** Anlatımdaki "pardon, onu yok say" cümleleri ve gösterimdeki dolambaçlar S1 ile işaretlenip otomatik ayıklanır; ayıklama kararları karar günlüğüne yazılır.
- **Yapılar için blueprint.** İnşa gösterimi, başlangıç noktasına göre göreli bir voksel planına çevrilir. Beceri "bu planı seçilen yere kur" olur.

### 4.4 Araştırma

- **Work2Skill** ([arXiv 2610.12984](https://arxiv.org/abs/2610.12984), 2026-10):
  - **Kayıt:** WorkRecorder ekran videosu, anahtar kareler, fare/klavye ve erişilebilirlik ağacını tek zaman çizgisinde hizalıyor.
  - **Beceri üretimi:** Ajan kanıtı ihtiyaç oldukça inceliyor. SKILL.md'ye iş akışı kuralları, adım bağımlılıkları, seçim kuralları, durma koşulları ve tamamlanma kontrolleri yazılıyor; değerler parametreye çevriliyor.
  - **Sonuç:** OSWorld'de +3–7.5, MyPCBench'te +4.7–10.5 puan.
  - **Ablasyon:** Görüntü, UI etiketi veya tuş logu çıkarılınca 5–11 puan kayıp.
  - **Eksiği:** Makale becerileri indirgemeli (downstream) olarak, jitter ve model transferiyle değerlendiriyor; ama üretim sırasında **kaydetmeden önce otomatik doğrulama/onarım kapısı yok**.
- **Hiyerarşik gösterim** ([arXiv 2606.20978](https://arxiv.org/abs/2606.20978)):
  - Düz log yerine **isimli alt hedef grupları** kullanmak, belirsiz görevlerde başarıyı %76.7'den %90.7'ye çıkarıyor.
  - Ön/son koşul ve parametre etiketleri ölçülebilir fayda sağlamadı.
- **ALLOY** (gösterim → graf iş akışı), **AWM** (izlerden iş akışı), **Skill-Pro** (ICML 2026; aktivasyon + yürütme + sonlanma koşulu).
- **VPT / NitroGen**: etiketsiz videodan aksiyonları geri çıkarma (ters dinamik). C seviyesi oyunlarda kayıt için.
- Minecraft'ta "insan oyununu kaydedip bot becerisine çeviren" **hazır çalışma bulunamadı** → özgün katkı.

### 4.5 Minecraft'ta kayıt yöntemi

| Yöntem | Ne yakalar | Artı | Eksi |
|---|---|---|---|
| **Kayıt proxy'si** (`minecraft-protocol` paketinin hazır `examples/proxy` örneği, v1.68) | İnsan client'ı ile sunucu arasındaki **tüm paketler**: kazma, yerleştirme, pencere tıklamaları (craft), elde tutulan eşya, hareket, envanter/blok güncellemeleri, **sohbet mesajları** | Vanilla sunucu + vanilla client, mod yok. Kesin. Metin anlatım bedava gelir (sohbet paketi, zaman damgalı). | Paket → olay çevirici yazmak gerek |
| Sunucu eklentisi (Paper) | Hazır anlamlı olaylar | Kolay olay | Java eklenti, Paper sunucusu |
| İzleyici bot | Sadece dünya değişimi | Basit | Envanter ve craft görünmez |
| Ekran kaydı | Video + girdi | Her oyunda çalışır | Minecraft'ta gereksiz kayıp |

**Öneri: kayıt proxy'si.** Oyuncu kendi Minecraft'ıyla `localhost:25566`'daki proxy'ye bağlanır; proxy gerçek sunucuya iletir.

**Anlatım kanalları (ikisi de desteklenir):**
- **Metin:** Oyun içi sohbete `// önce masa kur, gece olursa sığınağa gir` gibi notlar. Proxy zaten yakalıyor; `//` öneki anlatımı normal sohbetten ayırır.
- **Ses:** Mikrofon → yerel **Whisper** (Mac'te `whisper.cpp` veya `mlx-whisper`), kelime düzeyinde zaman damgasıyla olay zaman çizgisine hizalanır. İsteğe bağlı bir tuşla (push-to-talk) sadece anlatım anları kaydedilir.

### 4.6 Kayıttan beceri hattı (oyundan bağımsız)

```
0. NİYET         kullanıcı söylerse hedef + değişkenler; consult modunda bot sorabilir (zaman aşımlı), full modunda sormaz
1. KAYIT         adaptör olay akışı + durum anlık görüntüleri + anlatım (ses→metin veya // sohbet)
2. SOYUTLAMA     ham → anlamlı olay ("oak_log kırdı ×3", "planks craftladı ×4", "masa yerleştirdi")
                 konumlar → çapa noktasına göre göreli (oyuncu başlangıcı, yerleştirilen masa, hedef ağaç)
3. TEMİZLEME     S1: her anlatım cümlesi → {talimat, kural/hariç tutma, düzeltme("yok say"), sohbet}
                 S1: dolambaç/gereksiz eylem adayları → otomatik ayıkla, karar günlüğüne yaz
4. BÖLÜTLEME     isimli ALT HEDEFLER (hiyerarşik); sınır adayları kodla, sınır kararı S1 Noul ile
5. ÇIKARIM       S2 (frontier LLM): kod beceri + niyet kartı
                 her değeri sınıfla: zorunlu girdi / sabit sınır / gözlem / varsayım
                 inşa ise → blueprint + generic buildBlueprint çağrısı
6. BOŞLUKLAR    full: S2 boşlukları kendisi doldurur (hafıza + benzer beceriler + kanıt), varsayımları karta yazar, bildirir
                 consult: S2 takip soruları sorar (zaman aşımlı); cevap gelmezse full gibi
7. DOĞRULAMA     taze dünya (sabit seed) + parametre jitter'ı ile N tekrar; başarı = niyet kartındaki yüklem
                 başarısızsa: hata + kayıt kanıtı → S2 onarım (≤ 3 tur)
8. KARAR         Kaydet / Mevcut beceriyi güncelle (yeni sürüm) / At — full: doğrulama skoruna göre otomatik;
                 consult: öneri + zaman aşımlı onay. Her durumda sonradan geri alınabilir (düzeltme = ders)
9. KÜTÜPHANE     kaynak=demonstrated, kayıt bağlantısı, doğrulama skoru, sürüm
```

Değer önerisi: ajanın tek başına bulmakta zorlandığı becerileri (inşa, tarım, redstone, rota, savaş taktiği) **bir gösterimle** öğrenmek. Voyager'ın müfredatı bunları "görsel doğrulama gerekir" diye atlıyordu; bizde başarı yüklemini kaydın son durumu tanımlar.

**İnceleme sonrası eklemeler (§14):**
- **Anlam katmanları ayrı tutulur:** istemci isteği / sunucu onayı / gözlenen değişiklik / çıkarılan anlam. "Kesin paket" kesin niyet demek değildir: yerleştirme isteği reddedilmiş olabilir, oyuncu masayı tesadüfen ağacın yanına koymuş olabilir. Ham kayıt her zaman saklanır; L1 temizlemesi geri alınabilir bir işaretlemedir.
- **Kabul yüklemi bağımsızdır:** niyet kartındaki başarı yüklemi kod üretiminden önce ve ayrı yazılır; doğrulayıcı negatif örneklerle sınanır.
- **Genelleme testi:** sadece aynı seed'de jitter değil, görülmemiş arazi, malzeme, yön ve eksik ön koşullarla (karşı örnek fabrikası).
- **Aşamalı sıra (KARAR, Fatih 2026-10-15):** **v1** = deterministik **blueprint** (sunucu tarafı blok farkından, LLM'siz) + olaylardan isimli alt hedef makrosu. **v2** = davranışsal beceriler (tarım, savaş taktikleri) LLM ile parametreli koda, görülmemiş arazide doğrulanarak. İkisi de teslim kapsamında; v2, v1'in üstüne kurulur. Proxy önce spike S6 ile sınanır (configuration fazı, imzalı sohbet, craft'ın iki yolu).

---

## 5. Mimari: oyundan bağımsız çekirdek + oyun eklentileri

Karar (Fatih): sistem zamanla **diğer oyunlara evrimleşecek**. **Minecraft bir eklenti (plugin)** gibi düşünülür; çekirdek hiçbir oyunu bilmez. Bu, Fatih'in diğer projelerindeki "her şey bir eklenti" yaklaşımıyla da aynı çizgide (oh-my-llm, lokkum).

### 5.1 Büyük resim

```
┌───────────────────────────────────── ÇEKİRDEK / HOST (oyundan bağımsız, Python)     ─────────────────────────────────────┐
│                                                                                                                          │
│  Otonomi motoru (§5.7)    orchestrator · görev grafiği çalışma zamanı (§9) · yükseltme merdiveni (§6.3)                   │
│  Model katmanları (§6)    L1 DecisionClient (Jev / yerel) · L2 LlmClient (Haiku → Sonnet) · L3 eğitim hattı              │
│  Beceri sistemi (§8)      kütüphane · sözleşme · yaşam döngüsü · test koşucusu · arama + L1 yeniden sıralama             │
│  Hafıza (§7)              yer kayıtları · kaynak defteri · depo hafızası · olay günlüğü + RAG · dersler/kararlar          │
│  Kayıt hattı (§4)         soyutlama → temizleme → bölütleme → çıkarım → doğrulama (oyundan bağımsız aşamalar)             │
│  Kişilik (§10)            persona · ruh hali · anlatım · günlük                                                           │
│  Değerlendirme + telemetri  test setleri · ablasyon koşucusu · S1-Bench · token/$/ms                                     │
│  Arayüz kabuğu            CLI · web panosu (eklentiler kendi panellerini ekler) · ses (STT/TTS)                          │
│                                                                                                                          │
└──────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────┘
                                           │  Game Plugin Protocol (sürümlü, JSON-RPC; ayrı süreç)     
         ┌─────────────────────────────────┼──────────────────────────────────┬─────────────────────────────────────┐
         ▼                                 ▼                                  ▼                                     ▼
  minecraft eklentisi (A)         vizdoom eklentisi (A, sonra)       retro eklentisi (A, RAM okuma)       desktop-pixel eklentisi (C)
  TS · Mineflayer                 Python · ViZDoom                   Python · stable-retro / PyBoy        ekran + girdi · Jev Box · NitroGen
```

Çekirdeğin kendisi de eklenti noktalarıyla genişler, sadece oyunlar değil:
- **Model sağlayıcıları:** Jev, Unsloth yerel, Claude…
- **Hafıza arka uçları**
- **Ses motorları:** Whisper, TTS
- **Arayüz panelleri**
- **Persona paketleri**

### 5.2 Oyun eklentisi sözleşmesi

Bir oyun eklentisi iki parçadan oluşur: **manifest** (statik tanım) ve **bileşenler** (çalışan parçalar).

**Manifest** (örnek alanlar):

| Alan | Minecraft örneği |
|---|---|
| `id`, `version`, `protocolVersion` | `minecraft`, `0.1.0`, `gpp/1` |
| `game` + desteklenen sürüm aralığı | Java Edition `1.21.11` |
| Entegrasyon seviyesi | `A` (durum API'si) |
| Beceri dili / çalışma ortamı | `javascript` (node:vm sandbox) |
| Yetenekler (capabilities) | `observe, act, runSkill, interrupt, predicates, record, scenario, reset, memoryExtractors, knowledge` |
| Koordinat uzayı | `xyz + dimension(overworld|nether|end)` |
| Güvenlik varsayılanları | Korunan bloklar, yasak eylemler, sınırlar |

**Bileşenler**: eklentinin çekirdeğe sağladıkları.

| Bileşen | Ne sağlar | Çekirdekte kim kullanır |
|---|---|---|
| **Çalışma zamanı adaptörü** | `observe`, `act`, `runSkill`, `interrupt`, `reset`, olay akışı | Yürütücü, L1 monitörü |
| **Primitive kataloğu** | Tipli primitive'ler + LLM'e gösterilecek sade imzalar ve örnekler | L2 kod yazıcı, görev grafiği |
| **Durum şeması + projeksiyonlar** | Hangi L1 sorusuna durumun hangi alanları gider; sayısal/geometrik ön hesap ("zombi: 3.2 blok, 40° sol") | L1 DecisionClient |
| **Yüklem kütüphanesi** | `inventory.has`, `isNight`, `insideEnclosure`… | Doğrulayıcı, görev grafiği koşulları |
| **Bilgi sağlayıcı** | Hedef → gereksinim grafiği (Minecraft: tarif ağacı → `obtain` çözücüsü), fizibilite kontrolü | Müfredat, L2 kademesi, görev derleyici |
| **Sözlük** | Yer türleri (village, portal, mine…), varlık/eşya ontolojisi, tehlike türleri | Hafıza, L1 soru kriterleri |
| **Hafıza çıkarıcıları** | Olaylardan yer kaydı / kaynak defteri / epizodik olay adayları | Hafıza |
| **Senaryo kurucu** | Durumu programla kurma (MC: `/give`, `/tp`, `/summon`, `/fill`) | Beceri testleri, sentetik veri (L3), değerlendirme |
| **Kayıt yakalayıcı** | İnsan gösterimini anlamlı olay akışına çevirme (MC: protokol proxy'si) | Kayıt hattı |
| **Başlangıç becerileri** | Elle yazılmış çekirdek beceriler + `obtain` (§8.4) | Beceri sistemi |
| **L1 soru paketi** | Oyuna özel soru tanımları (tehlike türleri, modlar) — çekirdeğin genel soru şablonlarını doldurur | Soru kayıt defteri |
| **Prompt parçaları** | L2'ye oyunun API'si, kuralları, ipuçları | LlmClient |
| **Komut sözlüğü** | `#kaz`, `#git`, `#takip` gibi kısa komutlar → beceri eşlemesi | Görev derleyici |
| **Persona tadı** (isteğe bağlı) | Oyuna özel replikler ve tepkiler | Kişilik |
| **Arayüz paneli** (isteğe bağlı) | prismarine-viewer 3D görünüm | Web panosu |

**Çalışma zamanı protokolü** (önceki "Game Adapter Protocol"un genişletilmiş hâli):

| Metot | İş |
|---|---|
| `handshake()` | Manifest + protokol sürümü + yetenek pazarlığı |
| `observe(projection?)` | Yapılandırılmış durum (JSON) + isteğe bağlı kare. Sayısal/geometrik hesaplar burada yapılır. |
| `act(primitive, args)` | Tek primitive (L1 refleks kararları için) |
| `runSkill(code, deps, timeoutMs)` | Beceri kodunu eklentinin sandbox'ında çalıştırır; olay akışı + sonuç döner |
| `interrupt(reason)` | Çalışan beceriyi keser |
| `checkPredicate(pred)` | Deterministik yüklem |
| `knowledge.requirements(goal)` | Gereksinim grafiği / fizibilite |
| `scenario.setup(spec)` | Test veya sentetik veri için durum kurma |
| `startRecording()` / `stopRecording()` | Gösterim yakalama |
| `reset({ seed, mode })` | Tekrarlanabilir başlangıç |
| `events` (akış) | Oyun olayları: hasar, ölüm, envanter değişimi, sohbet, blok değişimi… |

**Zorunlu çekirdek vs isteğe bağlı yetenekler** (inceleme sonrası): her eklentinin uygulaması gereken **ince çekirdek** `handshake, observe, act, runSkill, interrupt, reset, events`'tir. `checkPredicate`, `knowledge`, `scenario`, `record` ve manifest'teki diğer bileşenler **isteğe bağlı yeteneklerdir**; çekirdek, yeteneği olmayan eklentide ilgili özelliği kapatır (örn. piksel eklentisinde kesin yüklem veya reset olmayabilir). Sözleşme önce Minecraft eklentisinin içinde TS arayüzleri olarak olgunlaşır, ikinci oyun spike'ıyla (S8) sınanır.

**Neden süreç sınırı?** Beceri kodu oyunun kendi dilinde çalışmak zorunda (Minecraft → Node, ViZDoom → Python, Unity modları → C#). Eklenti **her zaman ayrı bir süreçtir** (her dil olabilir). Süreç içi yükleme yolu inceleme sonrası kaldırıldı (§14): LLM'in yazdığı bir senkron döngü olay döngüsünü kilitlerse çekirdek, L1 monitörü ve telemetri de dururdu.

**Beceri yürütme izolasyonu:** beceri kodu eklenti içinde de ayrı bir **yürütme süreci/işçisinde** çalışır:
- API anahtarı yok; dosya ve ağ erişimi kısıtlı; CPU/bellek limiti var.
- Oyun işlemleri sadece izin denetimli bir **primitive aracısı** üzerinden yapılır; her primitive çağrısında iptal kontrolü var.
- Watchdog dış süreçte: kilitlenmede yürütücüyü öldürür, bot bağlantısını koruyarak veya yeniden kurarak devam eder.
- Statik kurallar: `await` içermeyen döngü yasak; `bot.chat('/…')` ile oyun komutu yasak; `require`/`process` erişimi yok.
- Ajan botu sunucuda **op değildir**. Senaryo kurulumu ve reset sadece değerlendirici/senaryo kurucunun **RCON** bağlantısıyla yapılır.
- Node belgelerine göre `vm` bir güvenlik mekanizması değildir ve zaman aşımı async işleri kapsamaz ([Node vm](https://nodejs.org/docs/latest-v22.x/api/vm.html#timeout-interactions-with-asynchronous-tasks-and-promises)). Ayrı süreç de tek başına güvenlik sınırı değildir; yukarıdaki kısıtlarla birlikte anlamlıdır.

### 5.3 Sınır kuralı: ne çekirdekte, ne eklentide?

| Çekirdekte (bir kez yazılır) | Eklentide (oyun başına) |
|---|---|
| Orchestrator, görev grafiği motoru, tetikleyiciler | Primitive'ler, komut sözlüğü |
| L1/L2 istemcileri, yükseltme merdiveni, Haiku→Sonnet kademesi | L1 soru paketinin oyuna özel kriterleri, L2 prompt parçaları |
| Soru **şablonları** (tehlike, ilerleme, mod, beceri seçimi) | Bu şablonların durum projeksiyonları |
| Beceri kütüphanesi, sözleşme şeması, yaşam döngüsü, test koşucusu | Beceri kodu, senaryo kurucu, yüklemler |
| Hafıza deposu, RAG, tazelik, unutma | Sözlük, hafıza çıkarıcıları, koordinat uzayı |
| Kayıt hattının oyundan bağımsız aşamaları | Kayıt yakalayıcı, ham → anlamlı olay çevirici |
| Persona motoru, ruh hali | (isteğe bağlı) oyuna özel replikler |
| Telemetri, değerlendirme koşucusu, S1-Bench, eğitim hattı | Oyuna özel test görevleri ve metrikler |

**Kural (AGENTS.md'de de var):** çekirdek kodunda hiçbir oyun adı, blok veya eşya adı geçmez. Geçiyorsa yanlış katmandadır.

### 5.4 Diğer oyunlara evrim

- **Eklenti sırası** (her biri çekirdeğin genelliğini farklı bir eksende sınar):
  1. **minecraft** (A, TS): ilk ve "mükemmel" hedefli prototip.
  2. **vizdoom** (A, **Python**): farklı dil, gerçek zamanlı aksiyon; Jev Doom deneyleriyle doğrudan kıyas.
  3. **retro** (A, RAM okuma; Game Boy/NES, stable-retro / PyBoy): 2D, farklı koordinat uzayı, SpeedrunBench ve Pokémon kıyasları.
  4. **desktop-pixel** (C): API'si olmayan herhangi bir oyun. Algı Jev görüntü/Box + VLM ile, refleks politikası NitroGen olabilir. Cradle'ın yolu.
- **Sağlık metrikleri** (inceleme sonrası düzeltildi): "çekirdekte değişen satır ≈ 0" tek başına yanıltıcı, çünkü aşırı genel bir JSON arayüzü de sıfır değişiklik verir ve karmaşıklığı eklentilere iter. Bakılacaklar: **eklenti geliştirme süresi**, eklentiler arası **tekrarlanan kod**, gereken **kaçış yolları** ve aynı görevde **davranış uyumu**. İlk sürümlerde sözleşmenin değişmesi başarısızlık sayılmaz. Değişiklik gerekiyorsa bu bir sözleşme eksiğidir; sözleşme sürümlenerek genişletilir (`gpp/1` → `gpp/2`), eski eklentiler çalışmaya devam eder.
- **Uyum test kiti (conformance kit):** her eklentinin geçmesi gereken otomatik testler (handshake, observe şeması, interrupt süresi, predicate doğruluğu, reset tekrarlanabilirliği). Bir oyuna eklenti yazan kişi çekirdeği okumak zorunda kalmaz.
- **Eklenti tarafı:** Minecraft eklentisi TypeScript (Mineflayer JS olduğu için); Doom eklentisi Python (ViZDoom). Protokol dil bağımsız; Unity/C# gerekirse sonra.
- **Oyunlar arası transfer:**

  | Taşınan | Nasıl |
  |---|---|
  | Model katmanları, kademe, otonomi motoru, hafıza motoru, kişilik | Doğrudan (çekirdek) |
  | L1 soru şablonları | Doğrudan; kriterler eklentiden |
  | **Ortak beceri kavramları** | Soyut niyetler (topla, git, savaş, kaç, sakla, inşa et, keşfet) her eklentide somut becerilere eşlenir. Pipeline'lar ve dersler bu kavramlarla yazılırsa başka oyuna da taşınır. |
  | L1 karar modelleri | Ortak taban model + oyun başına fine-tune (§6.7); yeni oyunda soğuk başlangıç için taban model veya Jev |
  | Dersler | Oyun-genel olanlar ("büyük kayıptan sonra önce güvenliği sağla") taşınır; oyuna özel olanlar ("creeper'lar sessiz yaklaşır") eklentide kalır |

### 5.5 Teknoloji seçimleri

| Konu | Öneri | Gerekçe |
|---|---|---|
| Çekirdek | **Python 3.13** (uv, ruff, pyright strict, pytest) — KARAR (Fatih, 2026-10-15) | Fatih'in tercihi ve öğrenme dili (kurs Python); ML ekosistemi aynı dilde (TypeSafe Python SDK, Unsloth, Whisper, istatistik, ViZDoom). Eklentiler zaten ayrı süreç olduğu için Mineflayer'ın JS olması çekirdeği etkilemez. |
| Minecraft eklentisi dili | **TypeScript (strict), Node 22** | Mineflayer ve beceri kodu JS dünyasında; beceriler TS + `tsc` ile tip kontrolünden geçer |
| Eklenti protokolü | Sürümlü JSON-RPC (stdio/WebSocket), **ayrı süreç**; ince zorunlu çekirdek + isteğe bağlı yetenekler | Dil bağımsızlığı + izolasyon (§14) |
| System 2 LLM | `LlmClient`; **Sonnet 5.5 varsayılan**, Haiku 5.5 metin işleri; kademe ve Opus S5'te ölçülür (§6.8) | Fatih kararı (inceleme sonrası) |
| System 1 | `DecisionClient` (§6.5): Jev + Unsloth karar modeli + logit + NLI + kural | Karar noktası başına ölçülür (§6.6) |
| Embedding | Yerel (PC'de) | Ücretsiz, hızlı |
| Depo | SQLite (+ sqlite-vec gerekirse) | Basit, yerel |
| **Mindcraft'tan ödünç parçalar** (KARAR) | Üstüne kurulmaz; Minecraft eklentisine alınır: test edilmiş beceriler ve dünya yardımcıları (primitive + başlangıç becerileri), Mineflayer eklentilerine yapılan yamalar, ViaProxy kurulumu, görev JSON formatı. MIT lisansı; alınan her dosya kaynak ve sürümüyle kaydedilir | Altyapı süresini kısaltır, "çekirdek oyun bilmez" kararını bozmaz. Spike S1'de birlikte denenir |
| **minecraft eklentisi** | mineflayer 4.39.x, MC Java **1.21.11** sabit; Docker `itzg/minecraft-server` (offline, sabit seed, localhost); kayıt için `minecraft-protocol` proxy; beceri yürütmesi ayrı kısıtlı süreçte + primitive aracısı + watchdog (§5.2); bot op değil, senaryo/reset RCON ile; prismarine-viewer paneli | Test edilen sürüm; Mindcraft ve MCP sunucusuyla uyumlu; Java kurmadan çalışır |

### 5.6 Voyager'a göre iyileştirmelerimiz

1. **Gerçek zamanlı System 1 monitörü** (Jev / yerel): beceri çalışırken tehlikeye tepki → easy/normal zorlukta hayatta kalma.
2. **Deterministik doğrulama önce**, sonra S1 Noul, en son LLM critic → daha ucuz ve daha güvenilir.
3. **Fizibilite kontrolü** (eklentinin bilgi sağlayıcısı) → uydurma görevler elenir.
4. **Başarısızlıktan ders** (MineEvolve remedy fikri).
5. **Record a skill** → Voyager'ın atladığı inşa ve yerleştirme becerileri.
6. **Kütüphane hijyeni**: sürümleme, yinelenen beceri tespiti, regresyon (skill drift), onarım.
7. **Sandbox + timeout + kesme**.
8. **Ölçüm baştan gömülü** (token, $, ms her çağrıda).
9. **Oyundan bağımsız çekirdek**: Voyager Minecraft'a gömülüydü; bizde Minecraft bir eklenti.
10. **Ayarlanabilir otonomi**: `full` modda hiç soru yok; diğer modlarda sorular zaman aşımlı, bot asla kilitlenmez (§5.7).

### 5.7 Otonomi seviyeleri: "asla sormaz" bir seçenektir

Karar (Fatih): bot tamamen otonom karar verebilmeli. **"Asla sormaz" bir seçenek** olarak sunulur, tek ve zorunlu bir davranış değildir. Otonomi seviyesi kullanıcı tarafından seçilir: varsayılan olarak, görev bazında veya pipeline bazında.

Literatürdeki karşılığı: Feng ve ark.'ın "Levels of Autonomy for AI Agents" çerçevesi ([arXiv 2506.12469](https://arxiv.org/abs/2506.12469)). Bu çerçeveye göre otonomi, yetenekten bağımsız bir **tasarım tercihidir**. Tam otonomi düşük riskli ve hızın kritik olduğu işlere uygun görülüyor ([kaynak](https://concepts.dsebastien.net/concept/human-out-of-the-loop/)). Hugging Face ekibi ise tam otonom ajanlara karşı çıkıyor ([özet](https://aiweekly.co/node/9510)). İkisini de karşılamak için seviye ayarlanabilir.

| Seviye (ayar) | Feng karşılığı | Bot ne zaman sorar? | Cevap gelmezse |
|---|---|---|---|
| **`full` — Tam otonom** | L5 Observer | **Asla.** Sorma → karar ver → kaydet → raporla | — |
| **`approver` — Riskli işlerde sorar** | L4 Approver | Sadece önceden tanımlı riskli durumlarda: geri alınamaz eylem, korunan bölgeye yakın iş, değerli eşya harcama | Zaman aşımı (örn. 30 sn) → riskli adım **yapılmaz**: atlanır, alternatif seçilir veya görev güvenle sonlandırılır. **Zaman aşımı yeni yetki vermez.** |
| **`consult` — Danışır** | L3 Consultant | Belirsiz komut, kayıt sonrası boşluklar, uzun görev öncesi plan onayı | Zaman aşımı → otonom karar |

**Temel kural: soru hiçbir zaman botu kilitlemez.** `approver` ve `consult` modlarında her sorunun:
- bir **zaman aşımı**,
- bir **varsayılan cevabı** (botun kendi otonom kararı)

vardır. Bot cevabı beklerken güvenli davranışta durur (savunma, bekleme). Süre dolunca kendi kararıyla devam eder. Böylece en danışkan modda bile AFK'da takılı kalmaz. **İletişim tercihi ile yetki ayrıdır:** otonomi seviyesi sadece *ne zaman sorulacağını* belirler; *neyin yapılmasına izin verildiğini* politikalar belirler. Zaman aşımı hiçbir zaman politikanın yasakladığı bir şeye izin vermez.

**Mod önerileri:**
- AFK / pipeline görevleri: varsayılan `full`.
- Öğretme (record a skill): varsayılan `consult`. Kullanıcı zaten başında; takip soruları anlamlı.
- İlk kurulum / güven kazanma dönemi: `approver`.
- Seviye görev başına ezilebilir: `#kaz demir 64 --otonomi=full`.

**Davranış seviyeye göre:**

| Durum | `full` | `approver` | `consult` |
|---|---|---|---|
| Belirsiz komut ("demir getir": kaç tane? nereden?) | En makul yorumu seçer (L1 Choice + geçmiş tercihler + bağlam), varsayımı kaydedip rapora yazar | `full` gibi | "Kaç tane?" diye sorar; süre dolarsa `full` gibi |
| Uzun AFK görevi başlarken | Bilgi amaçlı geri okur, hemen başlar | `full` gibi | Geri okur, onay ister; süre dolarsa başlar |
| Geri alınamaz eylem | Önceden konmuş politika karar verir; izin yoksa yapılmaz, alternatif aranır | **Sorar**; süre dolarsa yapılmaz (alternatif veya sonlandırma) | Sorar; süre dolarsa yapılmaz |
| L1 de L2 de emin değil | Güvenli varsayılan eylem (dur, savun, geri çekil) | `full` gibi | Kısa bir "şunu mu yapayım?" sorar, beklerken güvenli davranır |
| Kayıttan beceri | Takip soruları yerine varsayımlarını bildirir; Kaydet/Güncelle/At kararını doğrulama skoruyla kendisi verir | `full` gibi | Takip soruları sorar (§4.6 adım 6); Kaydet/Güncelle/At için öneri sunar; süre dolarsa `full` gibi |

**Tüm seviyelerde geçerli dört güvence:**
1. **Önceden konmuş sınırlar:** oyuncu kuralları ("evimin bloklarını kırma"), korunan bölgeler, görev guard'ları ve bütçeleri, eklentinin güvenlik varsayılanları. `full` modda onayın yerini bunlar alır.
2. **Geri alınabilirlik tercihi:** eşit fayda varsa geri alınabilir seçenek; geri alınamaz eylemler daha yüksek güven eşiği ister.
3. **Karar günlüğü:** her önemli karar gerekçesi, varsayımları, güven skoru ve **sorulduysa soru/cevap/zaman aşımı** ile yazılır.
4. **Acil durdurma ve sonradan düzeltme:** `#dur` her an çalışır. "Bunu yanlış yaptın" düzeltmesi ders/tercih olarak hafızaya girer.

**Ölçüm:**
- `full` modda "soru/onay isteği = 0" kabul kriteridir.
- Diğer modlarda soru sayısı, cevaplanma oranı ve zaman aşımı oranı raporlanır.
- Mod karşılaştırması rapora değer katar: aynı görev setinde `full` ile `consult` arasında başarı, süre ve kullanıcı müdahalesi farkı.


---

## 6. Model katmanları: Jev + frontier LLM entegrasyonu

Temel ilke: **her karar, onu yeterince iyi yapan en hızlı ve en ucuz katmanda verilir.** Bir üst katmana sadece alt katman emin değilse çıkılır. Bütçe kısıtı yok (Fatih); ama hız gerçek zamanlı oyunda bütçeden daha sert bir kısıt, ölçümü de rapor için zaten tutuyoruz.

### 6.1 Dört katman

| Katman | Kim | Süre | Sıklık | Ne için |
|---|---|---|---|---|
| **L0 Refleks** | Düz kod | 0–10 ms; acil tehlike olay → eylem ≤100 ms | her tick | Yol bulma, nişan, mesafe/açı, tarif zinciri (`minecraft-data`), başarı yüklemleri, durum çıkarımı. **Modelin asla yapmadığı işler.** |
| **L1 System 1** | **Jev** / yerel karar modeli | hedef p95 ≤300 ms | **olay tetikli**, tek uçuş (pratikte en fazla ~2–3 Hz) | Küçük, tipli, bağlamsal kararlar: seç, evet/hayır, puanla. Acil tehlike kararı **değil** (o L0'da). |
| **L2 System 2** | **Frontier LLM**: Sonnet 5.5 varsayılan, Haiku 5.5 metin işleri (§6.8) | 2–60 sn | görev başına birkaç kez | Kod yazma ve onarma, plan, müfredat, kayıttan beceri çıkarma, başarısızlık analizi. |
| **L3 Çevrimdışı** | Frontier LLM + eğitim | dakikalar–saatler | oturum aralarında | S1 için veri etiketleme, sentetik senaryo, fine-tune, kütüphane bakımı, değerlendirme. |

**Tek gecikme bütçesi (inceleme sonrası):** acil tehlike olaydan eyleme ≤100 ms (L0, 1–2 tick); L1 kararı p95 ≤300 ms; taktik karar uçtan uca (olay → gözlem → karar → kesme → sunucunun eylemi uygulaması) p95 ≤500 ms; L2 çağrıları asenkron, refleks yolunu asla bloklamaz. Belgedeki diğer tüm sayılar bu tanıma bağlıdır.

### 6.2 Karar noktaları haritası

| # | Karar noktası | Katman | Primitive / çıktı | Neden bu katman | Yedek |
|---|---|---|---|---|---|
| 1 | Tehlike var mı? (yaratık, düşme, lav, boğulma) | **L0** (L1 gölgede) | kural + zamanlayıcı; L1 Noul sadece gölge modda veya **bilinmeyen** varlık/durum için | Sayısal karar; Jev sayısal işlerde zayıf ve 300 ms gecikme acil tepki için fazla (§14) | — |
| 2 | Tehlikede ne yapmalı? | **L0 ilk tepki**, **L1 taktik** | L0 hemen kaçar/savunur; ardından olay tetikli L1 Choice {devam, geri çekil, savaş, ye, sığın, S2'ye sor} | İlk 100 ms kodun; bağlamsal taktik seçim modelin. Değer testi S4 ile ölçülür | L0 kural; güven düşükse en güvenli seçenek |
| 3 | Kontrol modu (topla / gez / savaş / sıkıştım / bekle) | **L0** durum makinesi (L1 gölgede) | L1 Choice sadece öneri | Blocks.ai'de de fazı **motor verisi** seçiyor, model sadece yerel yönü seçiyordu | — |
| 4 | İlerleme var mı, takıldı mı? | **L1** | Noul (son N gözlem + görev) | Sürekli izleme; takılınca S2'ye yeniden planlama tetikler | L0 sayaç (konum/envanter değişmedi) |
| 5 | Hangi beceri? (alım + yeniden sıralama) | L0 + **L1** | embedding top-20 → Choice + beceri başına Noul "uyar mı?" | TypeSafe skill suggestion tarifi: yanlış yükleme %16.8 → %7.3 | Sadece embedding |
| 6 | Oyuncu komutu ("bana odun getir") → beceri + argüman | **L1** | Choice (beceri) + argüman seçimleri | Yoldaş modunda anında tepki; argüman adaylarını kod çıkarır, model seçer | L2 |
| 7 | Görev bitti mi? (deterministik yüklem yoksa) | L0 → **L1** → L2 | yüklem → Noul → LLM critic | Ucuzdan pahalıya | — |
| 8 | Müfredat: hangi görev sırada? | **L2** üretir, **L1** puanlar | S2 10 aday önerir → Score (zorluk, yenilik, fayda) → kod seçer | Üretim yaratıcılık ister, puanlama hızlı ve paralel | S2 kendisi seçer |
| 9 | Beceri kodu yaz / onar | **L2** | kod | Sadece güçlü kod modeli yapabilir (Voyager, MindForge bulguları) | daha güçlü L2 modeli |
| 10 | Uzun ufuk planı (elmas → alt hedefler) | **L2** | yapılandırılmış plan | Akıl yürütme ister | — |
| 11 | Başarısızlık analizi → ders (remedy) | **L2** | metin + etiket | Açıklama ve genelleme ister | — |
| 12 | Kayıt: anlatım cümlesi türü | **L1** | Choice {talimat, kural, düzeltme, sohbet} | Çok sayıda kısa cümle; hızlı ve ucuz | L2 |
| 13 | Kayıt: alt hedef sınırı mı? | L0 aday + **L1** | Noul | Aday çok, karar küçük | L2 |
| 14 | Kayıt: beceri + niyet kartı + varsayım listesi | **L2** | kod + kart | Sentez işi | — |
| 15 | (C seviyesi oyunlar) ekranda hedef nerede, kare değişti mi? | **L1** | Box (Jev 1.14), görüntülü Noul | Hızlı görsel karar | VLM (L2) |
| 16 | Hafıza yazma: hatırlanmaya değer mi, kayıtlı yerle aynı mı, kayıtla çelişiyor mu? | L0 aday + **L1** | Noul ×3 | Sık ve küçük kararlar (§7.2) | L0 kural (mesafe eşiği) |
| 17 | Hangi kaynağa / hedefe git? (bilinen maden, yeni mağara, keşif) | **L0** fayda hesabı + **L1** seçim | Choice | Hesap kodda, bağlamsal seçim modelde (§7.3) | En yüksek L0 faydası |
| 18 | L2'de Haiku yeter mi, Sonnet mi? | **L0** kural (+ L1 sadece eşik olarak) | kural; Jev Score kalibrasyonu sayısal olarak zayıf, sadece eşik olarak kullanılır | Ön yönlendirme (§6.8) | Haiku dene, tetikleyiciyle yükselt |

**Değer testi (kural):** Her L1 karar noktası, aynı karar için elle yazılmış L0 kuralıyla karşılaştırılır. `jev-plays-doom`'da Jev elle yazılmış nişan kuralıyla **aynı** skoru aldı. Böyle bir noktada model sadece gecikme ve bağımlılık ekler, bu yüzden L0'da kalır. Model, kuralın kaçırdığı **anlamsal** durumlarda (yeni düşman tipi, alışılmadık zemin, oyuncunun belirsiz komutu) değer katmalı; bu da ölçülerek gösterilmeli.

### 6.3 Yükseltme merdiveni (escalation)

```
L0 kural kesin mi? ──evet──► uygula
   │ hayır/kural yok
L1 sor ──güven ≥ τ_soru──► uygula
   │ düşük güven
L1 tekrar: seçenek sırası karıştırılmış + farklı sağlayıcı (Jev ↔ yerel) ──uyuşuyor──► uygula
   │ uyuşmuyor / hâlâ düşük
güvenli varsayılan eylem (dur, savun, geri çekil) + L2'ye asenkron sor
   │ L2 cevabı gelince
uygula; (durum, sorular, L2 cevabı) → L3 eğitim verisi
```

- **`full` modda insan bu merdivenin basamağı değildir** (§5.7). Son basamak güvenli varsayılan eylem + asenkron L2'dir. `approver`/`consult` modunda insana zaman aşımlı bir soru eklenebilir; süre dolarsa yine bu son basamak uygulanır.
- Eşikler `(soru, sağlayıcı, model sürümü, projeksiyon)` dörtlüsü başına **ölçülerek** belirlenir; sağlayıcıların güven değerleri birbiriyle karşılaştırılamaz (Unsloth da eşiklerin sağlayıcılar arası taşınmamasını söylüyor). İki sağlayıcının anlaşması doğruluk sayılmaz; ortak hatalar ayrıca ölçülür.
- TypeSafe dokümanına göre güven skoru "harekete geçme izni" değildir, sadece dağılımın ne kadar yoğun olduğunu gösterir.
- **Seçenek sırası etkisi** (Jev'in bilinen zayıflığı): kritik sorular karıştırılmış sırayla iki kez sorulur (self-consistency tarifi).
- **Tazelik kontrolü:** L1 cevabı geldiğinde durum anlamlı ölçüde değişmişse (örn. düşman öldü, konum 3+ blok değişti) cevap atılır.

### 6.4 Çalışma zamanı entegrasyonu

```
            ┌──────────── Orchestrator (görev döngüsü, async) ────────────┐
            │                                                             │
  L2 istek kuyruğu ◄── yeniden planla / kod yaz / onar ◄─────┐            │
  (asenkron, iptal edilebilir)                               │            │
            │                                                │            │
            ▼                                                │            │
  Executor ── runSkill(code, AbortSignal) ──► Adaptör ──► oyun            │
            ▲                        │ olaylar                            │
            │ interrupt(reason)      ▼                                    │
  L1 karar döngüsü (olay tetikli, tek uçuş; acil tehlike L0'da)         │
     observe() → durum projeksiyonu → soru paketi (tek istek, paralel) ───┘
     → cevaplar + güven → yükseltme merdiveni → kes / devam / mod değiştir
```

- **L1 soruları tek istekte paralel** sorulur (tehlike, eylem, ilerleme). Jev bağımsız soruları aynı geçişte cevaplıyor, ek soru sadece token maliyeti.
- **L2 asla refleks döngüsünü bloklamaz.** L2 düşünürken bot L1/L0'ın seçtiği güvenli davranışta bekler.
- **Primitive'ler iptal edilebilir** (her primitive iptal sinyali dinler). Voyager'da bu yoktu, kod bitene kadar bot tepkisizdi. Ama iptal **kooperatiftir**: pathfinder'ın `stop()` metodu sonraki düğümü bekler, dig ve collectblock'un ayrı durdurma API'leri var. Bu yüzden primitive aracısı her birini kendi durdurma yoluyla sarmalar ve kesme **onayı** bekler.
- **Tek eylem sahibi (eylem hakemi):** beceri, L0 refleksleri, L1 kararları ve pipeline tetikleyicileri botu doğrudan yönetmez; **önerir**. Hakem açık önceliklerle (acil güvenlik > oyuncu komutu > tetikleyici > görev) tek bir sahip seçer, kaynak sahipliğini (hareket, el, envanter) yönetir. Kesilen işin geç gelen sonuçları **atılır** (iş kimliği/nesil numarası). "Devam et"ten önce ön koşullar yeniden doğrulanır. Gece + düşük can + dolu envanter aynı anda tetiklenirse tek bir "eve dön" planı çalışır.
- **L1 gölge modu:** yeni bir L1 karar noktası önce sadece öneri üretir, uygulamaz; L0 ile ayrıştığı durumlar loglanır. Değer testini geçince etkinleşir.
- **Durum projeksiyonu:** her soruya sadece ilgili alanlar verilir (Jev'in uzun ve alakasız durumda bozulması). Mesafe, açı ve sayımlar L0'da hesaplanıp **hazır** verilir ("zombi: 3.2 blok, 40° sol"), model sayı hesaplamaz.

### 6.5 Tek arayüz: `DecisionClient` + soru kayıt defteri

- **`DecisionClient`** TypeSafe'in istek biçimini (durum + sorular → tipli cevap + olasılıklar + güven) kopyalar. Sağlayıcılar:

| Sağlayıcı | Nasıl | Not |
|---|---|---|
| `typesafe` | Jev 1.13 / 1.14, resmî SDK | **API anahtarı var** (Fatih) |
| `unsloth-local` | Unsloth ile fine-tune edilmiş karar modeli; Decision API `jev-latest` adlı istekleri yerel modele yönlendirebiliyor, cevaplar Laya biçiminde | TypeSafe SDK ile birebir uyum **doğrulanmadı** (§14); ince bir adaptör gerekebilir |
| `logit-local` | Blocks.ai yöntemi: base model, tek ileri geçiş, harf logit'leri üzerinde softmax (MLX / llama.cpp) | Eğitim gerektirmez |
| `nli-local` | GLiClass / DeBERTa-v3 NLI | Çok hızlı, CPU'da çalışır; niyet ve anlatım sınıflama için |
| `llm-structured` | Frontier LLM + yapılandırılmış çıktı | Doğruluk üst sınırı referansı (yavaş) |
| `rules` | L0 kuralı | Taban çizgisi |

- **Soru kayıt defteri:** her karar noktası sürümlü bir **soru tanımıdır**: `id`, talimat, kriterler, durum projeksiyon fonksiyonu, seçenek sırası politikası, eşik, yedek, değer testi sonucu. Telemetri her çağrıyı `(soru_id, sürüm, sağlayıcı, durum, cevap, güven, gecikme, sonuç)` olarak loglar. Bu log hem benchmark'ın hem fine-tune verisinin kaynağıdır.

### 6.6 System 1 model karşılaştırması: Jev mi, yerel mi?

**Aday modeller** (araştırma bulguları):

| Aday | Tür | Beklenti | Kaynak |
|---|---|---|---|
| Jev 1.13 / 1.14 | Kapalı karar modeli | 70–500 ms, $0.042/Mtok; sayma ve seçenek sırası zayıf | TypeSafe docs |
| Unsloth karar modeli: Qwen3.5-0.8B / 2B / 4B, Gemma 4 E4B | LoRA + Clef tarzı sınıflandırma başlığı; olasılık + kalibrasyon (ECE) | Genel veride %77–81 (Unsloth kendi raporu); **oyun verisiyle fine-tune edilince** asıl kazanç | [Unsloth](https://unsloth.ai/docs/new/train-your-own-decision-model-with-unsloth) |
| Gemma 4 12B base + logit okuma | Sıfır atış | M4 Mac'te 113 ms medyan, eğitimsiz | Blocks.ai |
| DiffusionGemma + vLLM yaması | Açık "Jev klonu" | İlk karşılaştırmalarda Jev'le kabaca başa baş (doğrulanmadı) | ikincil |
| GLiClass (modern-base / edge), DeBERTa-v3-large NLI | Sıfır atış encoder | Çok hızlı; durum muhakemesinde zayıf olabilir, metin sınıflamada güçlü | [GLiClass](https://arxiv.org/abs/2508.07662), [BTZSC](https://arxiv.org/abs/2603.11991) |
| Fine-tune ModernBERT / DeBERTa encoder | Etiketli veriyle | Sabit etiket kümesinde LLM'lerden 10–1000× hızlı, eşit veya daha iyi; yeni etikete genellemez | [arXiv 2602.06370](https://arxiv.org/abs/2602.06370), [arXiv 2608.20371](https://arxiv.org/abs/2608.20371) |
| Claude Haiku/Sonnet 5.5 yapılandırılmış çıktı | Frontier LLM | Doğruluk referansı; gerçek zamanlıda yavaş | — |
| L0 kural | Kod | Taban çizgisi | — |

**Benchmark tasarımı (S1-Bench, oyun başına):**
- **Veri:** her karar noktası için 200–500 durum. Kaynaklar: gerçek oyun logları + sentetik senaryolar (§6.7). Etiketler: kural ile kesin hesaplanabilenler + sonuçtan (counterfactual) etiketlenenler + frontier LLM öğretmen etiketleri (insan tarafından örneklem denetimli).
- **Metrikler:**
  - Doğruluk ve makro-F1.
  - **Kalibrasyon** (ECE, güvenilirlik eğrisi).
  - p50/p95 gecikme (kendi donanımımızda, soğuk ve sıcak önbellek).
  - Seçenek sırası tutarlılığı.
  - Çağrı başı maliyet.
  - **Oyun içi etki**: aynı seed'de hayatta kalma ve görev başarısı.
- **Karar kuralı:** her karar noktası için Pareto (doğruluk × gecikme) en iyisi seçilir. Farklı noktalar farklı sağlayıcı kullanabilir (örn. anlatım sınıflama `nli-local`, tehlike monitörü Jev veya fine-tune Qwen).

### 6.7 Oyuna özel fine-tune ve sentetik veri (veri çarkı)

Oyunlar sentetik veri için ideal, çünkü **simülatör elimizde**: durumu biz kurabiliyor ve sonucu ölçebiliyoruz.

```
1. SENARYO ÜRETİMİ  S2 + kod: rastgele ama anlamlı durumlar kur
                    (Minecraft: /summon, /tp, /effect, /time, /give ile: 2 zombi 5 blokta, can 6, gece, kılıç yok…)
2. ETİKETLEME       a) kural/oracle (hesaplanabilen sorular)
                    b) COUNTERFACTUAL (sadece tek karar noktasında pilot; §14): aynı senaryoyu her seçenekle ÇOK KEZ oynat,
                       sonuç dağılımını ölç (hasar, ölüm, ilerleme); Minecraft deterministik değil, tek deneme gürültü öğretir
                       UYARI: "3 sn içinde hasar" etiketi seçilen eyleme bağlıdır (doğru kaçış tehlikeyi "tehlikesiz" gösterir)
                       → tehlike etiketi ile politika sonucu ayrı tutulur
                    c) frontier LLM öğretmen (gerekçeli) — insan örneklem denetimi
                    d) gerçek oyun logları + sonradan gelen sonuç (hindsight: "3 sn içinde hasar aldı mı?")
3. VERİ SETİ        Unsloth formatı: {state, questions, gold}; soru tanımları kayıt defterinden
                    eğitim / kalibrasyon (holdout) / test ayrımı; seed ve senaryo sızıntısı yok
4. EĞİTİM           Unsloth karar modeli (Qwen3.5 0.8B → 4B), LoRA r16, 2–4 epoch; calibrate() ile ECE
5. SERVİS           Decision API (Jev uyumlu) → DecisionClient'ta `unsloth-local`
6. KARŞILAŞTIRMA    S1-Bench + oyun içi A/B: Jev vs fine-tune vs sıfır atış
7. TEKRAR           yeni hatalar → yeni senaryolar (aktif öğrenme: düşük güvenli/uyuşmayan durumlar öncelikli)
```

- **Kayıttan gelen veri de girer:** oyuncunun gösterimdeki kararları (tehlikede ne yaptı) S1 için insan etiketidir.
- **Distillation hedefi:** L2'nin pahalı ama doğru kararlarını (örn. bulanık doğrulama, beceri seçimi) L1'e taşımak. L2 çağrı sayısı zamanla düşer; bu, raporda ölçülecek bir eğri.
- **Donanım:** eğitim ve yerel servis `fatih-pc`'deki RTX 5070 Ti (16 GB) üzerinde (§6.9).
- Bu kısım kursun **Model Damıtma (#42)** projesiyle örtüşüyor; raporda ayrı bir değer olarak sunulabilir.

### 6.8 Frontier LLM (L2): Sonnet 5.5 varsayılan, kademe ölçülerek

**Karar (Fatih, 2026-10-15, inceleme sonrası):**
- Kod yazma, onarım, plan ve kayıttan beceri için varsayılan **Claude Sonnet 5.5** (`claude-sonnet-5-5`).
- Yüksek hacimli metin işleri (özet, günlük, beceri açıklaması, hafıza yansıtması) **Claude Haiku 5.5** (`claude-haiku-5-5`).
- **Haiku → Sonnet kademesi** ve **Opus 5.5** (`claude-opus-5-5`) kod aşamasının ilk deneylerinden **S5'te ölçülür**. Kademe, başarıda tekil Sonnet'ten geri kalmayıp süre veya maliyette belirgin kazanç sağlarsa varsayılan olur. Opus, zor onarım ve kayıttan beceride Sonnet'i belirgin geçerse o işlerde kullanılır.

Gerekçe: kademenin amacı maliyet ve hızdı; bütçe kısıt olmayınca geriye hız kalıyor. Kademe ise Haiku başarısız olduğunda iki modelin süresini topluyor ve prompt önbelleğini model başına bölüyor (iki inceleyici, §14).

Aşağıdaki kademe tasarımı **S5'te ölçülecek aday** olarak duruyor. Kademe kazanırsa böyle çalışır: **ön yönlendirme ve sonradan yükseltme.**

1. **Ön yönlendirme (Haiku hiç denenmeden Sonnet'e gitmek):** Zor olduğu baştan belli olan işler doğrudan Sonnet'e gider. Kademe en kötü durumda iki modelin süresini toplar; bilinen zor işte Haiku'yu denemek sadece gecikme ekler.
   - Sabit kural: kayıttan beceri çıkarma, 2. başarısız denemeden sonraki kod onarımı, uzun ufuk planı → Sonnet.
   - L1 puanı: Jev'e "bu iş ne kadar karmaşık?" (Score) sorulur. Girdiler: benzer beceri var mı, kaç alt hedef var, bu görev daha önce kaç kez başarısız oldu, hafızada ilgili ders var mı.
2. **Sonradan yükseltme (Haiku denedi, sonuç kötü):** tetikleyiciler **ucuz ve nesnel** olmalı. Modelin "emin değilim" demesine güvenilmez.

   | Tetikleyici | Kontrol eden |
   |---|---|
   | Kod ayrıştırılamıyor, statik kural ihlali (`bot.on`, sonsuz döngü), olmayan primitive çağrısı | L0 (AST) |
   | Plan fizibilite kontrolünden geçmiyor (olmayan eşya, eksik tarif) | L0 (`minecraft-data`) |
   | Beceri sandbox'ta hata veriyor veya **2 denemede** başarısız | L0 + doğrulayıcı |
   | Haiku'nun kararı L1 makullük kontrolünde düşük çıkıyor ("bu plan bu durumda mantıklı mı?") | L1 Noul |
   | Haiku'nun iki örneği birbiriyle çelişiyor (kritik kararlarda) | kod |

3. **Ölçerek öğren:** Her yükseltme loglanır: hangi tetikleyici, Haiku sonucu, Sonnet sonucu, sonuçta ne oldu. **Signed Rescue Routing** ([arXiv 2609.07786](https://arxiv.org/abs/2609.07786); soyuttaki sonuçlar henüz "TBD", kanıt değil kavramsal uyarı olarak alınmalı) uyarıyor: büyük model, küçük modelin *doğru* cevabını da bozabilir. Bu yüzden yükseltmenin **net faydası** ölçülür; fayda getirmeyen tetikleyici kaldırılır. Veri birikince yönlendirici L3'te öğrenilmiş bir modele dönüşebilir ([cascade routing, ICML 2025](https://icml.cc/virtual/2025/poster/46183); [routing/cascading survey](https://arxiv.org/abs/2603.04445)).

**Varsayılan iş dağılımı (karar; S5 sonucuyla güncellenecek):**

| İş | Varsayılan model | Not |
|---|---|---|
| Müfredat aday üretimi, QA önbelleği | Sonnet | Kademe adayı: Haiku önce, fizibilite tutmazsa Sonnet |
| Basit beceri kodu (bilinen kalıp, benzer beceri var) | Sonnet | Kademe adayı: Haiku önce, `tsc`/statik hata veya 2 başarısız denemede Sonnet |
| Kod onarımı (3. deneme ve sonrası) | **Sonnet** | Opus adayı (S5) |
| Uzun ufuk planı, alt hedeflere bölme | **Sonnet** | — |
| Kayıttan beceri + niyet kartı + varsayım listesi | **Sonnet** | Opus adayı (S5) |
| Başarısızlık analizi → ders | Sonnet | — |
| Hafıza yansıtması, gün özeti, beceri açıklaması | Haiku | — |
| LLM critic (yüklem ve L1 yetmezse) | Sonnet | Doğrulanmış başarıyla aynı sınıfta tutulmaz |
| L3 öğretmen etiketleme | **Sonnet** (gerekçeli) | — |

- Her iki model de `LlmClient` arkasında; prompt caching açık (sistem prompt'u ve primitive dokümanı uzun ve tekrarlı).
- **S5 deneyi ve rapor ablasyonu:** sadece Haiku / sadece Sonnet / sadece Opus / kademe → başarı, deneme sayısı, duvar saati, toplam maliyet.

### 6.9 Donanım yerleşimi

Fatih'in iki makinesi var: **Mac** (geliştirme) ve **`fatih-pc`** (NVIDIA **RTX 5070 Ti, 16 GB VRAM**).

| İş | Nerede | Not |
|---|---|---|
| Unsloth karar modeli eğitimi | PC (5070 Ti) | Qwen3.5 0.8B / 2B / 4B rahat sığar (4–8 GB); Gemma 4 E4B (~14.4 GB) sınırda |
| Yerel L1 servis (karar modeli), embedding, Whisper | PC | Mac ↔ PC yerel ağ gecikmesi birkaç ms; L1 bütçesine (≤300 ms) sığar |
| Minecraft sunucusu (Docker) + bot | Mac veya PC | Gerçek oyun client'ı ile kayıt için Fatih'in oyun kurulu makinesi |
| Jev, Haiku, Sonnet | Bulut API | — |

---

## 7. Oyun hafızası: dünya haritası + RAG

İstek (Fatih): bot oyun geçmişini, envanteri, verilen kararları ve en basitinden **evin ve portalın konumunu** bilmeli; nerede köy gördüğünü, nerede ne bulduğunu hatırlamalı; **tükenmiş bir madene boşuna geri gitmemeli.**

### 7.1 Ana fikir: hafıza tek bir RAG değil

"Evim nerede?" sorusunun cevabı bir koordinat, "madene gitmeli miyim?" sorusununki ise bir hesap. Bunları vektör aramasıyla bulmak hem yavaş hem güvenilmez. Bu yüzden hafıza, **sorgu türüne göre** ayrı depolara bölünür. RAG sadece serbest metin geçmişi için kullanılır:

| Hafıza türü | Ne tutar | Nasıl sorgulanır | Katman |
|---|---|---|---|
| **Mekân hafızası** (yer kayıtları) | Ev, yatak, portal (bağlı çifti ile), köy, maden, sandık, tarla, yapı, tehlike bölgesi: tür, koordinat + boyut (overworld/nether/end), ad, ilk görülme, son ziyaret, **son doğrulama**, durum (aktif/tükendi/yıkıldı/bilinmiyor), kaynak (gözlem / oyuncu söyledi / çıkarım) | **Yapılandırılmış sorgu, kod** (L0): "en yakın aktif köy", "eve yol maliyeti" | L0 |
| **Kaynak defteri** | Bölge/chunk başına görülen cevherler (konumlarıyla), kazılanlar, kalan tahmini, taranmış hacim | Kod: beklenen verim / (yol + kazma süresi) | L0 hesaplar, L1/L2 seçer |
| **Eşya ve depo hafızası** | Sandık içerikleri (zaman damgalı), "demirim nerede?" | Kod: eşya → sandık listesi | L0 |
| **Epizodik hafıza** (olay günlüğü) | Ne, nerede, ne zaman: "3. gün (x,y,z) köy buldu", "creeper'dan öldü", "X görevi Y yüzünden başarısız" + gün/oturum özetleri | **RAG**: hibrit arama (BM25 + vektör) + filtreler (boyut, mesafe, zaman) | L1 sıralar, L2 okur |
| **Semantik hafıza** (dersler ve kararlar) | Remedy'ler, öğrenilen gerçekler ("bu dünyada çöl tapınağı batıda"), **kararlar + gerekçeleri** ("doğudaki madeni bıraktık çünkü tükendi") | RAG + etiket filtresi | L2 |
| **Prosedürel hafıza** | Beceri kütüphanesi (§5) | embedding + L1 yeniden sıralama | — |
| **Oyuncu kuralları ve tercihleri** | "Evimin bloklarını kırma", "ev burası", "geceleri dışarı çıkma" | Her zaman bağlamda (küçük, öncelikli liste) | L0 kural olarak uygulanır |

Bu ayrım iki çalışmayla örtüşüyor:
- **MrSteve** ([ICLR 2025](https://arxiv.org/abs/2411.06736)): Minecraft ajanlarının başarısızlığını epizodik hafıza eksikliğine bağlıyor ve **"ne-nerede-ne zaman" yer-olay hafızası** öneriyor. Ajan, hatırladığı olaylara göre keşif ile görev çözme arasında geçiş yapıyor.
- **EMem-Bench** ([arXiv 2609.28236](https://arxiv.org/abs/2609.28236), 2026-09): hafızayı mekân / olay / sahne olarak ayırıyor. Mevcut modellerin en zayıf olduğu yerler: **dinamik dünya durumunu takip etme** ve **etkileşim sonucu öğrenilen durumu kaydetme**. "Bu maden tükendi" tam olarak ikinci türden bir bilgi.

### 7.2 Yazma yolu: hafızaya ne, nasıl girer?

```
Adaptör olay akışı + periyodik tarama (findBlocks, yakın varlıklar)
   │
   ▼ L0 — kural tabanlı çıkarıcılar (otomatik, ucuz)
   │   köy:   köylü + çan + yatak kümesi        → yer kaydı adayı (village)
   │   portal: nether_portal blokları           → portal (boyut geçişinde bağlı çift eşlenir)
   │   maden:  cevher kümesi + kazma etkinliği  → kaynak defteri güncellemesi
   │   ölüm, hasar, envanter farkı, sandık aç/kapa → epizodik olay
   │
   ▼ L1 — küçük kararlar (Jev / yerel)
   │   "Bu hatırlanmaya değer mi?"                 (Noul, önem)
   │   "Bu, kayıtlı X yeriyle aynı yer mi?"         (Noul, birleştirme / tekrar önleme)
   │   "Bu gözlem kayıtlı bilgiyle çelişiyor mu?"   (Noul → geçersizleştirme)
   │
   ▼ L2 — yansıtma (Haiku; seyrek)
       gün sonu / oyuncu uyurken / oturum sonunda: olayları özetle, ders ve karar çıkar,
       yer kayıtlarına not ekle ("bu köyde demirci var")
```

- **Oyuncu doğrudan da yazabilir:** sohbete "burası ev" ya da `// ev burası` yazılınca o konum `home` olarak kaydedilir, kaynağı "oyuncu" olur ve en yüksek güveni alır. Kayıt sırasındaki anlatımla aynı kanal.
- **Kaynak defteri, "tükendi" kararının temeli.** Bölge başına görülen cevher − kazılan cevher ve taranmış hacim oranı tutulur. Görülen cevher kalmadıysa ve tarama kapsamı yüksekse bölge `exhausted` olur. Kapsam düşükse durum `unknown` kalır: "belki daha vardır" ile "kesin bitti" ayrılır.

### 7.3 Okuma yolu: hafıza nasıl kullanılır?

1. **Yapılandırılmış sorgular** (L0, milisaniye): `nearest(type="village", status="active", dimension="overworld")`, `chestsContaining("iron_ingot")`, `portalPair(id)`. Planlayıcı bunları **araç** olarak çağırır; beceri kodu da çağırabilir (`goTo(memory.home)`).
2. **Fayda hesabı** (L0): "demir lazım" →

   | Seçenek | Hesap | Sonuç |
   |---|---|---|
   | Bilinen maden A | 120 blok, kalan tahmini 2 cevher | düşük fayda |
   | Mağara B | 60 blok, 8 demir görülmüş, kazılmamış | **yüksek fayda** |
   | Yeni keşif | beklenen değer (biyom, y seviyesi) | orta |

   L0 tabloyu hesaplar; seçimi L1 yapar (bağlam: gece mi, envanter dolu mu) ya da L2 (uzun plan içindeyse). **"Tükenmiş madene gitme" davranışı böylece kendiliğinden çıkar**; ayrı bir kural yazmaya gerek kalmaz.
3. **RAG** (serbest geçmiş): "Daha önce bu bölgede ne oldu?", "Neden doğuya gitmeyi bıraktık?" → hibrit arama + filtre → L1 yeniden sıralama → en iyi birkaç kayıt.
4. **Bağlam paketi** (L2 prompt'ları için): her L2 çağrısına sabit bütçeli bir hafıza özeti eklenir: önemli yerler (ev, portal, aktif köy, en iyi kaynak noktaları), son olaylar, ilgili dersler, oyuncu kuralları. Paketi kod kurar, sıralamayı L1 yapar.

### 7.4 Tazelik, çelişki ve unutma

- **Zaman boyutlu geçerlilik:** her kayıtta `valid_from` / `valid_to` + `last_verified` var. Fikir Fatih'in Mnema hub'ındaki geçerlilik modelinden; ama oyun hafızası yüksek frekanslı olduğu için **ayrı, yerel** bir depoda tutulur.
- **Yeniden doğrulama:** bot kayıtlı bir yerin yakınından geçerken yer otomatik kontrol edilir ("portal hâlâ orada mı?"). Gözlem kayıtla çelişirse eski kayıt kapatılır, yenisi açılır; geçmiş silinmez.
- **Çelişki kuralı:** daha yeni **doğrudan gözlem** kazanır. Çıkarım, gözlemi ezemez. Oyuncu bilgisi ancak yeni bir gözlemle değişir.
- **Unutma:** "Remember the Decision, Not the Description" ([arXiv 2605.10870](https://arxiv.org/abs/2605.10870)): hafıza, olayların tam tarifini değil **kararları değiştiren ayrımları** saklamalı. Uygulaması:
  - Yer kayıtları ve kararlar asla silinmez, sadece bayat diye işaretlenir.
  - Eski epizodik olaylar gün ve hafta özetlerine sıkıştırılır.
  - Hiçbir karara girmemiş ham olaylar zamanla atılır.

### 7.5 Genellik: oyundan bağımsız hafıza çekirdeği

- Çekirdek hafıza API'si oyunu bilmez. **Yer** = `{tür, koordinat, uzay}`. Tür sözlüğü (village, portal, mine…) ve koordinat sistemi (Minecraft: x,y,z + boyut; Doom: harita + x,y; 2D oyun: oda + x,y) **adaptörden** gelir.
- L0 çıkarıcılar adaptörde yazılır (köy tespiti oyuna özel); depo, sorgu, RAG, tazelik ve unutma çekirdekte kalır.
- Her hafıza kaydı `oyun + world_instance_id + episode_id + reset nesli` ile etiketlenir; **seed kimlik değildir**, sadece meta veridir (aynı seed'den kurulan iki dünya zamanla farklılaşır, reset sonrası eski hafıza sızmamalı). Farklı dünyaların hafızası karışmaz; ama **dersler** dünyalar arası taşınabilir ("creeper'lar geceleri tehlikeli").

### 7.6 Ölçüm (rapor için)

- **Hafıza görevleri** (test setine eklenir; MineNPC-Task ve EMem-Bench'ten esinlenerek):
  - "İki gün önce gördüğün köye dön."
  - "Elmasları hangi sandığa koyduk, getir."
  - "Nether portalından eve dön."
  - "Demir lazım" → tükenmiş madene **gitmemeli**.
- **Metrikler:**
  - İsabetli geri dönüş oranı.
  - **Boşa yol** (tükenmiş veya yok olmuş hedefe gidiş sayısı ve mesafesi).
  - Gereksiz yeniden keşif.
  - Hafıza sorgu gecikmesi.
- **Ablasyon:** hafıza kapalı / sadece RAG / yapılandırılmış + RAG. Beklenti: "sadece RAG" konum sorularında hata yapar. Bu, tasarım kararının kanıtı olur.

---

## 8. Beceri tasarımı: hızın asıl kaynağı

Fatih'in tezi: **beceriler çok iyi olursa her şey müthiş hızlanır.** Kanıtlar bunu destekliyor:
- **SkillsBench** ([arXiv 2602.12670](https://arxiv.org/abs/2602.12670)): elle hazırlanmış beceriler başarıyı ortalama %33.9'dan %50.5'e çıkarıyor (+16.6 puan). **En fazla 3 modüllük odaklı beceriler**, her şeyi içeren büyük paketlerden daha iyi. Beceri verilen küçük modeller, beceri verilmeyen büyük modellere yetişebiliyor.
- **Beceri seçimi:** 196 becerilik bir kütüphanede hepsini birden yüklemek %29.3 başarı verirken, göreve uygun alt kümeyi seçen bir yöntem %45.3'e çıkıyor ve daha az token harcıyor ([arXiv 2606.32025](https://arxiv.org/abs/2606.32025)).
- **AgentSkillOS** ([arXiv 2603.02176](https://arxiv.org/abs/2603.02176)): aynı beceri kümesiyle, becerileri DAG (bağımlılık grafiği) olarak düzenlemek düz çağırmaktan belirgin şekilde daha iyi.
- **SkillEval** ([arXiv 2608.06891](https://arxiv.org/abs/2608.06891)): beceri kalitesi iki yönlü: göreve uygunluk ve yeniden kullanılabilirlik.

### 8.1 Beceri hiyerarşisi

```
Seviye 4  RUTİN / PIPELINE   kullanıcı seviyesi orkestrasyon (§9): "AFK'dayken demir kaz, dolunca boşalt"
Seviye 3  BİLEŞİK BECERİ     sığınak kur, demir zırh seti, buğday tarlası kur, nether'e git
Seviye 2  TEMEL BECERİ       obtain(item, n), mineOre(type, n), smelt(item, n), goTo(place), fightOrFlee()
Seviye 1  PRIMITIVE          adaptörün elle yazılmış, test edilmiş çekirdeği (~15–40 adet)
Seviye 0  REFLEKS            pathfinder, pvp, nişan (Mineflayer eklentileri)
```

**En büyük hızlandırıcı: genel `obtain(item, n)` çözücüsü.** (İnceleme notu: bu küçük bir yardımcı değil, başlı başına bir **planlayıcı**. İlk sürüm sonlu bir eşya kümesini destekler; alternatif tarifler, yakıt, araç dayanıklılığı, istasyon erişimi ve envanter kapasitesi açıkça ele alınır; döngü tespiti, kaynak rezervasyonu ve açık `unsupported` / `unreachable` sonuçları vardır.)
- `minecraft-data` tarif grafiği üzerinden çalışır (GITM'in yaklaşımına benzer):
  - envanterde ne var, ne eksik;
  - eksik için hangi alt eşyalar gerekiyor (tarif ağacı);
  - hangi araç gerekiyor;
  - hammadde nerede (önce hafızadaki kaynak defteri, yoksa keşif).
- Hepsini **kod hesaplar** ve sırayla primitive'leri çağırır.
- Voyager'ın LLM'e tek tek yazdırdığı yüzlerce "craftX / mineY" becerisi tek bir deterministik çözücüye dönüşür. LLM'e sadece çözücünün beceremediği işler kalır: inşa, taktik, alışılmadık durumlar.

### 8.2 Her becerinin sözleşmesi

| Alan | Örnek |
|---|---|
| Ad + açıklama (görev diliyle) | `buildShelter`: "Gece için 5×5 kapalı sığınak kurar" |
| Parametre şeması | `{ size: 3–7, material?: blockName, near?: placeRef }` |
| Ön koşullar | ≥ 40 blok, açık alan |
| **Son koşul (deterministik yüklem)** | Bot kapalı bir hacmin içinde; kapı var. Yüklem koddan **önce ve bağımsız** yazılır, negatif örneklerle sınanır; belirsizse sonuç `unknown` |
| Yan etkiler | Blok tüketir, blok yerleştirir, yer kaydı ekler (`shelter`) |
| Tipli hata türleri | `missing_items`, `not_found`, `path_blocked`, `interrupted`, `timeout`, `unsafe` |
| İptal edilebilirlik | AbortSignal'e uyar; yarıda kesilince güvenli duruma geçer |
| Devam ettirilebilirlik | Yarım kalan inşayı kaldığı yerden sürdürür |
| Risk seviyesi + tahmini süre | Pipeline planlayıcısı ve L1 bu bilgiyi kullanır |
| Bağımlılıklar | Çağırdığı alt beceriler (DAG) |
| Kaynak | Elle yazılmış / öğrenilmiş / gösterimden / pipeline'dan terfi |
| Ölçümler | Başarı oranı, ortalama süre, hata dağılımı, kullanım sayısı |

### 8.3 Beceri yaşam döngüsü

```
taslak ──(senaryo testleri, parametre jitter'ı: N/N)──► doğrulanmış ──(gerçek oyunda k başarılı kullanım)──► güvenilir
   ▲                                                         │                                              │
   └────────────── onarım (S2) ◄─── başarısızlık / sürüm değişikliği (skill drift) ◄─────────────────────────┘
                                                                                     kullanılmıyor/yinelenen → emekli
```

- **Arama ve kullanım** varsayılan olarak sadece *doğrulanmış* ve *güvenilir* becerileri görür.
- **Senaryo testleri:** komutlarla kurulan küçük test dünyaları (/give, /tp, /fill) + son koşul yüklemi. Her gece veya her sürüm değişikliğinde **regresyon** koşar.
- **Beceri katkısı:** "beceriyle başarı − becerisiz başarı" ölçülür (NVIDIA SkillEvaluator'daki "Skill Lift" fikri). Katkısı olmayan beceri sadeleştirilir.
- **Yinelenenleri birleştirme / sadeleştirme:** Programmatic Skill Networks'teki refactor + geri almayla doğrulama fikri ([arXiv 2601.03509](https://arxiv.org/abs/2601.03509)).
- **Bağlama az ve odaklı beceri:** her L2 çağrısına en fazla 3–5 ilgili beceri, bağımlılık sırasıyla (SkillsBench + composer bulguları).

### 8.4 Başlangıç kütüphanesi (bootstrap)

ODYSSEY'nin yaptığı gibi **elle hazırlanmış bir çekirdek** ile başlanır: primitive'ler + `obtain` çözücüsü + ~20 temel beceri (savaş/kaç, ye, uyu, sandığa koy/al, eve dön, keşfet, ağaç kes, mağara bul). Öğrenme ve kayıt bu çekirdeğin **üstüne** inşa eder; her şeyi sıfırdan öğrenmeye çalışmak Voyager'ın pahalı ve yavaş yoluydu.

**Rapor için ölçüm:**
- Elmas kazmaya ulaşma süresi ve LLM çağrı sayısı, üç kolda: sıfırdan / çekirdekle / çekirdek + öğrenilmiş kütüphane.
- **"Saat başına LLM çağrısı" eğrisi:** kütüphane büyüdükçe düşmeli. Bu, "beceriler sistemi hızlandırıyor" tezinin doğrudan kanıtı.

### 8.5 Becerilerin dört kaynağı, tek standart

| Kaynak | Nasıl gelir | Aynı sözleşme ve test |
|---|---|---|
| Elle yazılmış | Geliştirici | ✓ |
| Öğrenilmiş | Voyager döngüsü (L2 kod yazar) | ✓ |
| Gösterimden | Record a skill (§4) | ✓ |
| Pipeline'dan terfi | Sık kullanılan bir pipeline beceriye derlenir (§9) | ✓ |

---

## 9. Komutlar, görevler ve pipeline'lar (AFK modu)

İstek (Fatih): "Oynadım, AFK kalacağım; bota *git maden kaz*, *düşman öldür*, *şunu bul* diyebilmeliyim." Bu doğal dille, sesle ya da bir pipeline kurarak olabilmeli.

### 9.1 Üç giriş kanalı, tek ara gösterim

```
 Doğal dil (oyun içi sohbet / web)  ─┐
 Ses (push-to-talk → Whisper)        ─┼──► GÖREV GRAFİĞİ (Task IR) ──► doğrula ──► geri oku (bilgi) ──► yürüt ──► rapor
 Pipeline (görsel editör / YAML)     ─┘          ▲                                                      │
                                                 └───────────── kaydet / zamanla / beceriye terfi ◄─────┘
```

**Görev grafiği (Task IR):** küçük, tipli bir davranış ağacı / DAG.

| Düğüm | Anlam | Örnek |
|---|---|---|
| `skill(ad, parametreler)` | Beceri çağrısı | `mineOre("iron_ore", 64)` |
| `sequence` / `fallback` | Sırayla yap / ilk başaranı kullan | Önce sandıkta ara, yoksa kaz |
| `loop(until | count | duration)` | Tekrar | Envanter dolana kadar |
| `condition(yüklem)` | Durum veya hafıza sorgusu | `night`, `health < 6`, `inventory.full`, `memory.exhausted(mine_A)` |
| `trigger(olay → alt grafik)` | Olay tetikleyicisi | Gece olunca → eve dön, uyu; envanter dolunca → sandık X'e boşalt |
| `guard` | Sınırlar | Evden en fazla 200 blok uzaklaş, oyuncunun yapılarına dokunma, risk ≤ orta |
| `budget` | Süre / mesafe / deneme sınırı | En fazla 2 saat |
| `report` | Bildirim politikası | Her 15 dk özet, bitince/hata olunca haber ver |

**Örnek:** "AFK'dayım; 64 demir kaz, envanter dolarsa eve dön sandığa boşalt, gece olursa uyu, canın 6'nın altına düşerse eve kaç, 2 saatte bitir"

```
budget(2h) ▸ guard(radius=200 from home, protect=player_builds)
  ├─ trigger(night)          → goTo(home.bed) ▸ sleep
  ├─ trigger(health < 6)     → fleeTo(home) ▸ eat ▸ wait(health ≥ 14)
  ├─ trigger(inventory.full) → goTo(chest:"maden sandığı") ▸ deposit(ores)
  └─ loop(until count(iron_ore|raw_iron) ≥ 64)
        └─ mineOre("iron_ore")   ◄ hedefi kaynak defteri seçer (tükenmiş madene gitmez, §7.3)
report(every 15m, on: done | fail | death)
```

### 9.2 Derleme: komuttan görev grafiğine

1. **Önce deterministik ayrıştırıcı.** Baritone tarzı kısa komutlar (`#kaz demir 64`, `#git ev`, `#takip et Fatih`) doğrudan grafiğe çevrilir. Model gerekmez, anında çalışır. (nekostulAICompanion da önce katı ayrıştırıcı, olmazsa LLM yolunu kullanıyor.)
2. **Basit doğal dil → L1.** "Bana odun getir" → Choice (beceri) + argüman seçimi, ~200 ms (karar noktası #6).
3. **Karmaşık doğal dil / ses → L2.** Haiku görev grafiğini yazar; belirsizlik ya da uzun koşullu görev varsa Sonnet (§6.8).
4. **Doğrulama (L0):**
   - Beceriler var mı, parametreler şemaya uyuyor mu?
   - Hafıza referansları çözülüyor mu ("maden sandığı" hangi sandık)?
   - Fizibilite: 64 demir için kazma var mı, yoksa grafiğe `obtain(stone_pickaxe)` eklenir.
   - Oyuncu kuralları ve güvenlik sınırları.
5. **Geri okuma:** "Anladığım: 64 demir, dolunca maden sandığına, gece uyu, can 6 altı eve kaç, 2 saat." Ses kanalında TTS ile okunur. `full` modda bot **beklemeden** başlar ve belirsiz kısımlarda varsayımını rapora yazar. `consult` modda onay ister; zaman aşımı dolarsa başlar. Kullanıcı her an `#dur` veya yeni bir komutla düzeltebilir (§5.7).

### 9.3 Yürütme motoru (oyundan bağımsız)

- **Davranış ağacı çalışma zamanı çekirdektedir.** Tetikleyiciler L1 monitörüyle aynı olay akışını dinler. Tetikleyici çalışınca o an çalışan beceri iptal edilir, tetikleyicinin alt grafiği çalışır, sonra ana döngüye dönülür.
- **Kalıcı durum:** pipeline durumu diske yazılır. Bağlantı koparsa veya bot ölürse kaldığı yerden sürer; ölünce eşyaları geri toplamak için standart bir `recoverDeath` alt grafiği çalışır.
- **Raporlama:**
  - Oyun içi sohbet, web panosu ve isteğe bağlı telefon bildirimi.
  - Dönünce **"AFK özeti"**: ne topladı, nerede ne buldu (hafızaya ne yazıldı), ne ters gitti.
- **Kaydet ve tekrar kullan:** "sabah rutini" (hasat + pişir + depola) adıyla kaydedilir, oyun-içi saat veya gerçek saatle zamanlanabilir.
- **Terfi:** çok kullanılan pipeline, sözleşmeli ve test edilmiş bir bileşik beceriye derlenir (§8.5).
- **Görsel editör:** web panosunda düğüm tabanlı editör (sürükle-bırak tetikleyici/koşul/beceri). Kayıttan gelen beceriler de birer düğüm olarak görünür.

### 9.4 Emsaller

- **Baritone** ([kullanım](https://git.psf.lt/0xf8/baritone/raw/branch/1.12.2/USAGE.md)): `#mine 64 diamond_ore`, `#goto`, `#follow`, `#farm`, waypoint kaydetme. Kanıtlanmış komut ergonomisi; ama koşul, tetikleyici ve hafıza yok.
- **AIBot "Bob"** ([kaynak](https://p.codekk.com/detail/6a033e245b02fc5c75bba05c)): "LLM planlar, deterministik görevler yürütür". Geriye zincirleme hedef planlayıcı + 44 bağımsız durum makinesi, her biri kendi watchdog'uyla. Bizim L2/L0 ayrımına çok yakın.
- **LLM ile davranış ağacı üretimi** (robotik, [arXiv 2302.12927](https://arxiv.org/abs/2302.12927)): doğal dilden ağaç üretip, hata çıkınca ağacı düzelten bir yorumlayıcı.
- **Wingman AI:** sesli oyun yoldaşı (STT/TTS, komut tanımları).
- **Güvenlik:** AFK bot sadece **kendi sunucumuzda**. Başka sunucularda AFK bot kuralları ihlal edebilir.

---

## 10. Yaratıcılık ve kişilik

### 10.1 İlham: GPT-6 Astra ve creeper olayı (Eylül 2026)

**Ne oldu?** Bağımsız değerlendirici **Vals AI**, OpenAI'ın GPT-6 Astra modelini Minecraft'ta 141 saatlik bir yayında oynattı. Haberlere göre sadece standart kontroller kullanıldı ([Dexerto](https://www.dexerto.com/minecraft/gpt-6-astra-forced-to-play-minecraft-gets-depressed-by-creeper-and-farms-potatoes-for-hours-3409634/), [Tom's Hardware](https://www.tomshardware.com/tech-industry/artificial-intelligence/defeated-gpt-6-astra-model-spent-several-hours-just-farming-potatoes-after-being-blown-up-by-a-creeper-in-minecraft-openai-offering-gets-further-than-any-other-ai-system-in-141-hour-test), [XDA](https://www.xda-developers.com/gpt-6-astra-made-amazing-progress-on-minecraft-until-a-creeper-blew-up-its-chest-and-it-spiralled-into-sadness/)).
- Model yarı otomatik bir blaze çiftliği kurdu, 6 blaze rod ve 3 ender pearl topladı.
- Değerli eşyalarını bir sandığa koyduktan sonra bir creeper **sandığı ve yatağı** patlattı; doğma noktası da gitti.
- Model saatlerce **sadece patates ekti**. Sonra "yeşil şeylerden" ürkmeye başladı; bir şeker kamışını creeper sandı ve kendine "YEŞİL uzun şey ŞEKER KAMIŞI, creeper DEĞİL!" diye not düştü.
- Kendine "kritik eşyaları koru, sandıkları korumasız bırakma" notu yazdı.
- Hikâye viral oldu; OpenAI'ın geliştirici hesabı da paylaştı.

**Düzeltme:** "Ölmeyi bekledi" ayrıntısı bulunan kaynaklarda yok; kaynaklarda anlatılan, saatlerce patates ekmesi. "Depresyon" da medyanın yorumu. Model duygu yaşamıyor; ama davranışı insanlara **duygusal bir hikâye gibi okundu**, değerli olan da bu.

**İki ders çıkıyor:**
1. **Mühendislik dersi:** Ajanın büyük kayıptan sonra **toparlanma planı** yoktu. Düşük riskli, tekrarlı bir işe kilitlendi.
2. **Ürün dersi:** İnsanlar ajanın tepkilerini **kişilik** olarak okuyor ve bu çok ilgi çekiyor. Demo videosu ve sunum için altın değerinde.

**Mimari doğrulaması — aynı ay iki deney daha:**
- **Ronak Malde** (2026-09-20, [ASCII.jp](https://ascii.jp/en/elem/000/004/436/4436545/)): **GPT-6 Astra (planlayıcı) + Jev (anlık eylem seçimi) + Mineflayer (yürütme)** ile Ender Dragon'u **8 dk 43 sn**'de kesti.
  - Astra 35 çağrı (~$0.96), Jev 131 çağrı (~$0.01); toplam < $1.
  - Astra arka planda planlarken Jev eylem seçmeye devam ediyor, oyun hiç durmuyor. Bu, bizim L2 + L1 + L0 ayrımımıza benzer bir entegrasyon (§6); ama öğrenme içermiyor ve bilinen bir rota kullanıyor (§2.5).
  - Ama: peaceful zorluk, önceden seçilmiş seed, rota ve koordinatlar; MC 1.16.5. Bizim hedefimiz bilinmeyen dünyada, zorlukla ve **öğrenerek**.
- **Vals AI CUA-Bench** (2026-09-18, [özet](https://hermes-ai.net/news/vals-ai-s-cua-bench-humbles-every-frontier-agent-below-20-points/)): sadece ekran + klavye/fare ile 6 oyun.
  - Hiçbir model 100 üzerinden 20'yi geçemedi; Minecraft'ta **hiçbir model demir bulamadı**.
  - Modeller 15–59 saniyede bir eylem yapıyor.
  - Bu, durum API'si + kod becerileri yolumuzun (A seviyesi) doğru tercih olduğunu bir kez daha gösteriyor.

### 10.2 Toparlanma: kayıp sonrası planı mühendislik olarak çözmek

- **Büyük kayıp algısı (L0):** ölüm, sandık veya yatak yok oldu, değerli eşya kaybı (envanter + hafıza farkı).
- **Post-mortem (L2):** ne kaybedildi (hafızadan liste), neden oldu, ders ne → semantik hafızaya "değerlileri ender chest'e koy / sandık çevresini kapat / yatağı korumalı yere koy" kuralları.
- **Toparlanma planı (L2):** "en hızlı geri dönüş" grafiği: eşya geri toplama süresi içindeyse önce ona koş, yoksa yeniden üretim sırası.
- **Kısır döngü tespiti (L1, karar noktası #4):** "son N dakikadır düşük değerli tekrarlı iş mi yapıyorum?" → evet ise yeniden planla. Astra'nın patates döngüsü tam bunun örneği.

### 10.3 Kişilik: isteğe bağlı bir özellik

Amaç, botun bir "karakter" olarak izlenmesini sağlamak. Kural: **kişilik oyunu sabote etmez**; oyuncunun açık komutlarını her zaman önceler ve "iş modu"nda tamamen kapatılabilir.

| Bileşen | Nasıl |
|---|---|
| **Persona** | İsim, konuşma tarzı, değerler ("meraklı kâşif", "temkinli inşaatçı", "şakacı"). Prompt + L1 eşiklerine küçük önyargılar. |
| **Ruh hali durumu** | Olaylardan türeyen, zamanla sönen sayısal değişkenler: *güven, korku, merak, can sıkıntısı, gurur*. Ölüm → korku↑; nadir buluntu → gurur↑; uzun tekrar → can sıkıntısı↑. |
| **Davranışa etkisi (sınırlı)** | Korku yüksekse risk eşiği düşer (geceleri dışarı çıkmaz). Can sıkıntısı yüksekse müfredat yenilik puanına ağırlık verir (Astra'nın patates döngüsünün tersi). Etkiler kodla sınırlandırılır ve loglanır. |
| **Anlatım** | Oyun içi sohbet / TTS ile kısa yorumlar: "Bu yeşil şey... şeker kamışı. Evet. Kesinlikle şeker kamışı." Önemli anlarda sesli tepki. |
| **Günlük** | Her oyun günü sonunda epizodik hafızadan L2 (Haiku) birinci ağızdan bir **günlük** yazar ("3. gün: mağarada az kalsın ölüyordum…"). Hafızanın insan tarafından okunabilir yüzü. |
| **Anı ve ilişki** | Oyuncuyla ortak geçmiş: "Geçen sefer burada beraber öldük." Hafızanın sosyal kullanımı. |
| **Öne çıkan anlar** | Telemetri "ilginç anları" işaretler (ölümden kıl payı kurtuluş, nadir buluntu, büyük kayıp) → demo videosu için otomatik klip zaman damgaları. |

Emsaller:
- **Project Sid:** küçük prompt dürtmeleriyle ajanlarda belirgin kişilik çeşitliliği ([MIT TR](https://www.technologyreview.com/2024/11/27/1107377/a-minecraft-town-of-ai-characters-made-friends-invented-jobs-and-spread-religion/amp/)).
- **MIMIC** ([arXiv 2510.01635](https://arxiv.org/html/2510.01635v1)): oyun ajanları görev tamamlamaya optimize edilince tekdüze ve tekrarlı davranıyor; kişilik özellikleri davranışı çeşitlendiriyor.

### 10.4 Yaratıcılık: kendi hedeflerini koyan bot

- **Merak müfredatı:** yenilik puanı (L1 Score), keşfedilmemiş biyomlar, hiç yapılmamış eşyalar. Voyager'ın "keşfi maksimize et" fikri, ruh hali ile ayarlanır.
- **Estetik inşa:** L2 (Sonnet), arazi ve biyomla uyumlu bir ev planı çizer → blueprint → `buildBlueprint` (§4.3'teki blueprint altyapısı tekrar kullanılır).
- **Oyuncuya sürpriz:** AFK dönüşünde "sana bir şey yaptım" anları (küçük bir kule, işaretlenmiş köy yolu). Sadece kişilik modunda ve oyuncu kurallarıyla sınırlı.
- **Kendine notlar:** Astra'nın "kritik eşyaları koru" notu gibi, ders çıkarıp kendi davranışını değiştirmesi zaten §7'nin semantik hafızası. Kişilik modunda bu notlar sohbette de görünür.

---

## 11. İlk prototip: Minecraft'ı "mükemmel" oynamak

**Kararlar (Fatih, 2026-10-15):**
- **Ana iddia: oynayarak öğrenme.** "Öğrenilmiş beceri kütüphanesi, botun hiç görmediği dünyalarda başarıyı düşürmeden süreyi ve LLM çağrısını azaltır." Gösterimden öğrenme ve AFK güvenilirliği destekleyici sonuçlar olarak raporlanır.
- **"Mükemmel" kademeli tanımlanır:**
  - **Ana hedef:** easy zorlukta, görülmemiş seed'lerde boş envanterden elmas kazma; normal zorlukta 3 oyun günü hayatta kalma; 25 görevlik test seti.
  - **Esnek hedef:** bilinmeyen bir dünyada, survival'da ve hazır rota olmadan **Ender Dragon**. Malde'nin denemesi bilinen seed, peaceful ve hazır portalla yapılmıştı.
  - Yoldaş davranışı AFK görevleriyle ölçülür.
- **Görünürlük iki mod:**
  - **Adil mod:** değerlendirme ve rapor için varsayılan. Bot sadece görüş hattındaki ve havaya bakan blokları bilir, gördüklerini hafızasına yazar.
  - **Tam bilgi modu:** AFK'da verimlilik için seçilebilir.
  - Mod her koşunun sonuç dosyasına yazılır; "mükemmel oynama" iddiası adil modda ölçülür.

"Mükemmel" ölçülebilir hedeflere bağlanmalı, yoksa bitiş çizgisi olmaz. Önerilen hedefler (Fatih onaylayacak). **İnceleme notu (§14):** her başarı oranı güven aralığıyla raporlanır; örneğin 8/10'un %95 Wilson aralığı [%49–94], 4/5'inki [%38–96]. Bu yüzden aşağıdaki küçük örneklemli hedefler tek başına iddia kanıtı sayılmaz; §11.1 protokolü geçerlidir.

| Hedef | Ölçüt | Hedef değer |
|---|---|---|
| Teknoloji ağacı (ana) | Boş envanterle, **easy** zorlukta, **adil modda**, görülmemiş 10 test seed'inde elmas kazmaya ulaşma | ≥ 8/10 seed, ≤ 60 iterasyon |
| Ender Dragon (esnek) | Bilinmeyen dünya, survival, adil mod, hazır rota/portal/sensör yok | En az 1 doğrulanmış koşu; süre ve LLM çağrısı raporlanır |
| Görev seti | ~25 görevlik test seti (4 kademe: ahşap → taş → demir → elmas/zırh/yemek/mob) | ≥ %90 başarı (öğrenilmiş kütüphaneyle) |
| Hayatta kalma | Normal zorlukta 3 oyun-günü (gece dahil) | Ölüm ≤ 1 |
| Tepki süresi | Acil tehlike: olay → eylem (L0) / taktik karar uçtan uca (L1) | ≤ 100 ms / p95 ≤ 500 ms (§6.1) |
| Hafıza | §7.6 hafıza görevleri; boşa yol (tükenmiş/yok olmuş hedefe gidiş) | Görevlerde ≥ %90; boşa gidiş ≈ 0 |
| L2 kademesi | Haiku→Sonnet kademesi vs tekil modeller | Başarıda Sonnet'e yakın, maliyet ve süre olarak ondan belirgin düşük |
| AFK pipeline | §9.1 örneği gibi 2 saatlik koşullu görev, gözetimsiz | Bitirme ≥ %90, ölüm 0, oyuncu yapısına zarar 0 |
| Beceri hızlandırması | §8.4: sıfırdan / çekirdek / çekirdek + kütüphane | Saat başına LLM çağrısı monoton düşüş; elmasa ulaşma süresi belirgin kısalır |
| Otonomi | `full` modda bot → kullanıcı soru/onay isteği | **0** (diğer modlarda soru, cevap ve zaman aşımı oranı raporlanır) |
| S1 kalitesi | Her L1 karar noktasında L0 kuralına karşı | Kuralı istatistiksel olarak geçmeyen nokta L0'a döner |
| Kayıttan beceri | 5 farklı gösterim (masa + fırın kurma, buğday tarlası, 3×3 sığınak, …) | Taze dünyada ≥ 4/5 başarılı tekrar |
| Maliyet | Elmas kazmaya kadar toplam model maliyeti | Raporla; hedef < $5/koşu |

**Ablasyonlar** (inceleme sonrası daraltıldı): önce **tek ana hipotez**: öğrenilmiş kütüphanenin katkısı. Ardından sırayla L1 (kural vs Jev; "S1 yok" kolunda L0 güvenliği **açık kalır**), hafıza (kapalı / sadece yapılandırılmış / yapılandırılmış + RAG), L2 (tekil Sonnet vs kademe). "Claude vs yerel L2" kolu kaldırıldı: MindForge bulgusu sonucu zaten öngörüyor.

### 11.1 Değerlendirme protokolü (inceleme sonrası)

- **Ön kayıt:** görev seti, seed'ler ve başarı yüklemleri değerlendirme başlamadan dondurulur. Prompt ayarı sadece geliştirme seed'lerinde yapılır.
- **Öğrenme ve test ayrı:** öğrenme seed'leri ≠ test seed'leri; testte kütüphane dondurulur. Çevrimiçi öğrenme ayrı bir deney olarak ölçülür.
- **Verilen vs öğrenilen:** elle yazılmış çekirdek (`obtain` dahil) ile öğrenilmiş beceriler ayrı raporlanır. Ana iddia: "öğrenilmiş kütüphane **görülmemiş** dünyada başarıyı düşürmeden süreyi ve L2 çağrısını azaltır".
- **Eşleştirilmiş karşılaştırma:** ana kollarda ≥20–30 eşleştirilmiş koşu (aynı seed + görev + başlangıç durumu). McNemar testi ve bootstrap güven aralığı; seed/görev kümelenmesi hesaba katılır. Örneklem büyüklüğü pilot varyanstan ve hedeflenen en küçük anlamlı farktan hesaplanır.
- **Kısa senaryolar ağırlıklı:** uzun koşular (elmas, 3 gün) az sayıda tutulur; ağırlık RCON ile kurulan 2–10 dakikalık senaryo görevlerinde. **Duvar saati bütçesi** tablosu tutulur (koşu başı süre, $, paralel sunucu sayısı; PC'de birden çok Docker sunucusu).
- **Ek metrikler:** duvar saati, başarı başına $, L2 p95, ölüm/saat, hasar, ilerlemesiz süre, p95/p99 tepki, **yanlış başarı bildirimi oranı**, çökme/kopma oranı ve müdahalesiz çalışma süresi, beceri yeniden kullanım oranı, hiç çağrılmayan beceri oranı.
- **Başarısızlıklar saklanır:** zaman aşımı, kopma ve doğrulayıcı belirsizliği rapordan çıkarılmaz.
- **S1 verisi:** ardışık 200–500 durum bağımsız örnek değildir. Nadir tehlikelerde kaçırma oranı, yanlış alarm ve karar vermekten kaçınma ayrıca ölçülür.
- **Otonomi:** "soru = 0" yapısı gereği her zaman doğrudur, ölçü değildir. Ölçülen: `full` modda **yanlış varsayım** sayısı, sonradan düzeltme sayısı ve geri alınamaz eylem sayısı.
- **Kayıttan beceri:** ölçü birimi "gösterim × N taze dünya tekrarı"; gösterim başına başarı oranı ± güven aralığı.

---

## 12. Yol haritası (5 hafta, teslim 2026-11-19)

**Çalışma şekli (KARAR, Fatih 2026-10-15):** kodu Claude yazar, Fatih inceler ve anlar. Her iş bir GitHub **issue** → dal → **PR** → Fatih incelemesi → merge akışıyla ilerler. Kurallar AGENTS.md "Çalışma akışı" bölümünde.

**Haftalık plan** (GitHub milestone'larıyla aynı):

| Hafta | Tarih (bitiş) | Hedef | Kapsam |
|---|---|---|---|
| **1** | 2026-10-22 | Botun ayakta ve güvenli olması | S1 uyumluluk, S2 sandbox/kesme, S3 doğrulayıcı/reset, M0 altyapı, M1 eklenti çekirdeği |
| **2** | 2026-10-29 | LLM ile ilk öğrenen döngü | S5 model seçimi, M2 görev döngüsü + değerlendirme iskeleti, M3 beceri kütüphanesi |
| **3** | 2026-11-05 | Keşif, hafıza, L1 | S4 Jev vs kural, S7 öğrenme katkısı, M4 müfredat + hafıza, M5 L1 |
| **4** | 2026-11-12 | Komut ve öğretme; ana ölçüm koşuları başlar | S6 proxy, M6 komut/AFK, M7 kayıt v1, M8 koşuları |
| **5** | 2026-11-19 | Rapor ve demo | M8 rapor (§11.1), M9 demo/video/sunum; zaman kalırsa genişletmeler |

**Dürüst değerlendirme:** "hepsi kalsın" kararıyla 5 hafta sıkı. Çekirdek ve kayıt v1 bu takvime sığar. Genişletmeler (M7b, M10) **öncelik sırasıyla** ve ancak zaman kalırsa girer:
1. `approver`/`consult` modları
2. Ses komutu + TTS
3. Kişilik anlatımı + günlük
4. Davranışsal kayıt (M7b)
5. Epizodik RAG
6. Görsel editör + zamanlama
7. L3 fine-tune
8. Ender Dragon esnek hedefi

Her hafta sonunda ana iddianın ölçümü güncellenir; teslim günü hangi noktada olursak olalım raporlanabilir bir sonuç olur. **Doom (M11) teslimden sonraki iştir.**


**Kilometre taşları** (haftalara dağılımı yukarıda). **Kapsam kararı (Fatih, 2026-10-15): vizyondaki her şey teslim kapsamında.** İki inceleyicinin takvim uyarısı bu yüzden sıralamayla yönetilir: önce uçtan uca çalışan ve ana iddiayı (oynayarak öğrenme) ölçebilen çekirdek (M0–M5, M8'in iskeleti M2'de), sonra genişletmeler. Her taş bitince ana iddianın ölçümü güncellenir; böylece hangi noktada durulursa durulsun elde raporlanabilir bir sonuç olur.

| Taş | İçerik | Bitti sayılır |
|---|---|---|
| **Spike'lar S1–S7** | §14.6 deneyleri (S8 ViZDoom, Doom işiyle birlikte teslim sonrası) | Her spike'ın kararı yazıldı (devam / değiştir / bırak) |
| **M0 Altyapı** | Python çekirdek iskeleti (uv) + TS Minecraft eklentisi iskeleti, CI (lint/tip/test), Docker MC 1.21.11 (RCON açık, bot op değil), bot bağlanıyor, viewer | Bot doğuyor, tarayıcıdan izleniyor |
| **M1 Eklenti çekirdeği** | ince protokol, ayrı süreç + watchdog + primitive aracısı, iptal edilebilir primitive'ler, eylem hakemi, L0 güvenlik refleksleri, bağımsız yüklemler, reset | Elle yazılmış beceri ile ahşap → masa; kesme/kopma testleri yeşil |
| **M2 Tek görev döngüsü + değerlendirme iskeleti** | L2 kod yazıcı (TS + `tsc`), test-önce yüklem, 4 deneme, telemetri + iz kimliği; **değerlendirme koşucusu** ve ilk 5 donmuş senaryo | "Craft a wooden pickaxe" sıfırdan; koşucu rapor üretiyor |
| **M3 Beceri kütüphanesi** | sözleşme, taslak→doğrulanmış (+ aday sürüm), senaryo testleri, sınırlı `obtain`, başlangıç çekirdeği | Öğrenilmiş beceri görülmemiş seed'de çağrılıyor (S7 ölçütü) |
| **M4 Müfredat + hafıza (yapılandırılmış)** | öneri + fizibilite + başarısızlık dersleri; yer kayıtları, sandık, kaynak durumu (`world_instance_id`) | 60 iterasyon keşif; "köye dön", "elmaslar hangi sandıkta" geçiyor |
| **M5 L1** | `DecisionClient` (kural + Jev + 1 yerel), soru kayıt defteri, gölge mod, olay tetikli taktik kararlar | Değer testini geçen noktalar etkin, diğerleri L0'da |
| **M6 Komut / AFK** | `#komut` ayrıştırıcı, L2 → Task IR, tetikleyici + guard + bütçe, kalıcı durum, AFK özeti | §9.1 örneği gözetimsiz bitiyor |
| **M7 Record a skill v1** | proxy kaydı, anlam katmanları, blueprint + alt hedef makrosu, `//` metin anlatım, bağımsız kabul yüklemi | Gösterilen sığınak görülmemiş arazide tekrar ediliyor |
| **M7b Record a skill v2** | davranışsal beceriler (tarım, savaş) LLM ile, görülmemiş arazide doğrulama, ses anlatımı (Whisper) | Gösterilen tarla/taktik farklı arazide tekrar ediliyor |
| **M8 Değerlendirme + rapor** | §11.1 protokolü, ana hipotez + sıralı ablasyonlar | §11 tablosu güven aralıklarıyla dolu |
| **M9 Demo + teslim** | dashboard, README, sabit "çekim seed'i", günlük + öne çıkan anlar, video, sunum | Teslim paketi hazır |
| **M10 Genişletmeler** (teslim kapsamında, sırayla) | `approver`/`consult` modları; ses komutu + TTS; görsel pipeline editörü + zamanlama + bildirim; kişilik/ruh hali; epizodik RAG + dersler; L3 (S1-Bench, Unsloth fine-tune, counterfactual pilotu); Ender Dragon esnek hedefi | Her biri kendi ölçütüyle (§8–§10) |
| **M11 İkinci oyun: Doom** (KARAR: teslimden sonraki iş) | ViZDoom eklentisi (Python) aynı çekirdekle; sonra retro ve piksel eklentileri | Sözleşme genellik metrikleri (§5.4) |

## 13. Riskler

| Risk | Önlem |
|---|---|
| Kapsam şişmesi: Fatih tüm vizyonu teslim kapsamında tuttu; iki inceleyiciye göre en büyük risk bu | Sıralama: önce ana iddiayı ölçen çekirdek (M0–M5), her taşta ölçüm güncellenir; genişletmeler (M7b, M10, M11) sonra. Teslim tarihi gelince elde her zaman raporlanabilir bir sonuç olur |
| Jev servisi kesilir / model sürümü davranış değiştirir | `DecisionClient` + yerel sağlayıcılar; soru tanımları sürümlü; model sürümü değişince S1-Bench yeniden koşulur |
| Hafıza bayatlar (maden tükendi, köy yıkıldı) → yanlış kararlar | Geçerlilik aralıkları, yakından geçerken yeniden doğrulama, yeni gözlem kazanır |
| Haiku sessizce yanlış yapar ve yükseltme tetiklenmez | Tetikleyiciler nesnel kontrollere dayanır; doğrulayıcı her sonucu ölçer; yükseltme logu düzenli incelenir |
| Kişilik özelliği işi bozar (korkup görevi bırakır, oyuncu komutunu geciktirir) | Ruh hali etkileri kodla sınırlı; oyuncu komutu her zaman öncelikli; "iş modu"nda kapalı |
| AFK pipeline gözetimsizken zarar verir (yapı kırar, kaybolur, ölür) | Guard'lar (yarıçap, korunan yapılar), bütçe, tetikleyiciler, kalıcı durum + ölüm kurtarma, düzenli rapor |
| Otonom bot yanlış yorumla geri alınamaz bir şey yapar | Önceden konmuş politikalar (yasaklar, korunan bölgeler), geri alınabilir seçenek tercihi, geri alınamaz eylem için yüksek güven eşiği, karar günlüğü |
| Eklenti sözleşmesi Minecraft'a göre şekillenir, diğer oyunlara uymaz | Sözleşme sürümlü; erken aşamada ViZDoom için kâğıt üstünde uyum kontrolü; çekirdekte oyun adı yasağı |
| LLM kodu olay döngüsünü kilitler / gizli kaynaklara erişir | Ayrı kısıtlı yürütme süreci, primitive aracısı, dış watchdog, statik kurallar (§5.2) |
| Bot yüklü chunk'ları "x-ray" gibi görür, değerlendirme haksız kolaylaşır | Görünürlük politikası (Fatih kararı, §14.4); bot op değil; `/` komutları yasak |
| Eklentiler bayat (pathfinder 2023, pvp 2022, viewer 1.21.4 dokuları) | Spike S1; gerekirse fork/yama bütçesi |
| Sohbet/tabela metni üzerinden prompt injection | Oyun içi metin durum verisi olarak işaretlenir, talimat sayılmaz |
| Fine-tune modeli oyun dağılımına aşırı uyar | Senaryo/seed sızıntısız ayrım, kalibrasyon holdout'u, oyun içi A/B ile doğrulama |
| LLM maliyeti (keşif modu uzun) | Görev ve oturum bütçe limiti, prompt caching, ucuz model ile açıklama/critic |
| S1 model hataları (sayma, mesafe, seçenek sırası) | Sayısal işler kodda; seçenek sırası karıştırma testi; güven eşiği altında kurala devret |
| Kayıt → beceri genellemesi zayıf | Hiyerarşik bölütleme + anlatım + taze dünyada doğrulama + onarım döngüsü |
| Mineflayer sürüm uyumsuzluğu / skill drift | MC sürümü sabit, package-lock, regresyon koşusu |
| LLM'in yazdığı kodun yerel makinede çalışması | Sandbox, sadece yerel offline sunucu, public sunucuya asla bağlanma |
| Rastgelelik → tekrarlanamaz sonuç | Sabit seed, hard reset, çoklu tekrar |

---

## 14. Dış inceleme: Opus 5.5 + GPT-6-Astra (2026-10-15)

İki bağımsız inceleyici aynı talimatla tüm belgeleri okudu ve sert bir eleştiri yazdı:
- **Claude Opus 5.5:** alt ajan, web doğrulamalı.
- **GPT-6-Astra:** Codex CLI, yüksek düşünme seviyesi, salt okuma.

Ham raporlar: [docs/reviews/2026-10-15-opus.md](reviews/2026-10-15-opus.md), [docs/reviews/2026-10-15-astra.md](reviews/2026-10-15-astra.md).

### 14.1 Ortak hüküm

> İki model de aynı sonuca vardı: **araştırma güçlü, ama tasarım bir kurs teslimi için fazla büyük; en büyük risk, öğrenmenin katkısını gösteren uçtan uca tek bir dilimin geç çıkması.** Doğru bulunanlar: deterministik doğrulama, "konum sorusu RAG değil kod" fikri, L0'a karşı değer testi, oyun eklentisi sınırı.

### 14.2 İki modelin de bulduğu sorunlar (yüksek güven) ve uygulanan düzeltmeler

| # | Sorun | Uygulanan düzeltme (bu belgede) |
|---|---|---|
| 1 | **Sandbox modeli yanlış.** `node:vm` zaman aşımı async kodu kesmiyor; LLM'in senkron bir döngüsü olay döngüsünü kilitliyor (fizik, keepalive, monitör birlikte duruyor). Yerel sunucu kullanmak geliştirici makinesini ve API anahtarlarını korumuyor. | Beceri yürütmesi **her zaman ayrı süreçte**: anahtarsız, dosya/ağ erişimi kısıtlı, kaynak limitli. Dış süreçte watchdog kilitlenmede süreci öldürüp yeniden bağlar. "Süreç içi TS eklentisi" yolu kaldırıldı. Primitive'ler izin denetimli bir aracıdan geçer, her çağrıda iptal kontrolü yapılır. AST kuralı: `await` içermeyen döngü yasak (§5.2, §5.5, karar #8). |
| 2 | **Tehlike monitörü L1'de yanlış katmanda.** Tehlike sayısal bir karar ve Jev sayısal işlerde zayıf. Tek uçuşlu çağrıda 300 ms gecikme en fazla ~3.3 Hz eder; 5 Hz sağlanamaz. Malde'nin deneyinde Jev ~0.25 Hz ve olay tetikli çalışıyor. | **Acil tehlike tepkisi L0'da** (kural + zamanlayıcı + pvp; olaydan eyleme hedef ≤100 ms). L1 **olay tetikli taktik seçim** ve dil-anlamsal noktalar için (komut→beceri, anlatım türü, beceri yeniden sıralama, kısır döngü). L1 önce **gölge modda** çalışır: önerir, uygulamaz; L0'dan nerede ayrıldığı loglanır (§6.1, §6.2, §6.4). |
| 3 | **Botu kim yönetiyor belirsiz.** Beceri, monitör ve tetikleyiciler aynı hareket ve envanteri yönetmeye çalışıyor (gece + düşük can + dolu envanter = üç ayrı "eve dön"). `AbortSignal` kooperatif; pathfinder'ın `stop()` metodu sonraki düğümü bekliyor. | **Tek eylem sahibi (eylem hakemi):** açık öncelikler, kaynak sahipliği, kesme onayı. Kesilen işin geç gelen sonuçları atılır; "devam et"ten önce ön koşullar yeniden doğrulanır (§6.4). |
| 4 | **Beceri kendi sınavını yazıyor.** Kodu, niyet kartını ve başarı yüklemini aynı çıkarım üretiyor; yanlış anlaşılan niyet, yüklemde de "başarılı" çıkar. | **Bağımsız doğrulama:** başarı yüklemi kod üretiminden **önce** ve ayrı yazılıp dondurulur (test-önce sentez). Doğrulayıcı negatif örneklerle sınanır (çatısız sığınak, erişilemeyen kapı, içeride düşman). Belirsiz sonuç `unknown` olarak kaydedilir, başarı sayılmaz (§8.2, §8.3). |
| 5 | **Öğrenmenin katkısı ölçülemiyor.** `obtain` çözücüsü + başlangıç becerileri teknoloji ağacını büyük ölçüde kodla çözüyor; öğrenme ve test aynı seed'lerde (sızıntı). | **Değerlendirme protokolü** (§11.1): öğrenme ve test seed'leri ayrı, test seti ve kütüphane dondurulur, elle yazılmış ve öğrenilmiş beceriler ayrı raporlanır. Ana iddia: "öğrenilmiş kütüphane **görülmemiş** dünyada L2 çağrısını ve süreyi düşürür, başarıyı düşürmez". |
| 6 | **İstatistiksel güç yok.** 8/10'un %95 Wilson aralığı [%49–94], 4/5'inki [%38–96]; 3 tekrar kolları ayırt etmiyor. | Ana kollarda ≥20–30 **eşleştirilmiş** koşu (aynı seed + görev), McNemar / bootstrap güven aralığı; daha az ablasyon, daha çok tekrar; ön kayıt (pre-registration) (§11.1). |
| 7 | **Dünya kimliği seed olamaz.** Aynı seed'den kurulan iki dünya zamanla farklılaşıyor; reset sonrası eski sandık/maden hafızası sızar. | Hafıza anahtarı `world_instance_id + episode_id + reset nesli`; seed sadece meta veri (§7.5, karar #11d). |
| 8 | **Counterfactual etiketleme gürültülü.** Minecraft deterministik değil; ayrıca "3 sn içinde hasar aldı mı" etiketi seçilen eyleme bağlı: doğru kaçış, tehlikeli durumu "tehlikesiz" etiketletir. | Counterfactual sadece **tek karar noktasında pilot**. Tehlike etiketi ile politika sonucu ayrı tutulur, çoklu tekrarla dağılım olarak bakılır, kural oracle'ı öncelikli (§6.7). |
| 9 | **API uyumu davranış uyumu değil.** Sağlayıcıların güven değerleri karşılaştırılamaz; Unsloth da eşiklerin taşınmaması gerektiğini söylüyor. "Unsloth Jev uyumlu, sadece adres değişir" iddiası doğrulanamadı. | Eşikler `(soru, sağlayıcı, model sürümü, projeksiyon)` dörtlüsüne bağlı. "İki model anlaştı" doğruluk sayılmaz, ortak hatalar ölçülür. Unsloth iddiası "doğrulanmadı" diye düzeltildi (§6.3, §6.5). |
| 10 | **Eklenti sözleşmesi tek oyundan çıkarılmış ve fazla geniş;** "çekirdek değişikliği ≈ 0" yanlış metrik (çok genel bir JSON arayüzü de sıfır değişiklik verir) ve teslimde ölçülemez. | **İnce zorunlu çekirdek** (`handshake, observe, act, runSkill, interrupt, reset, events`) + isteğe bağlı yetenekler. Genellik metriği: eklenti geliştirme süresi + tekrarlanan kod + gereken kaçış yolları. Sözleşme kâğıt üstünde değil, kod aşamasında **1 günlük ViZDoom spike'ıyla** sınanır. Teslim hedef tablosundan çıkarıldı (§5.2, §5.4, §11). |
| 11 | **`approver` zaman aşımı yetki genişletiyor.** "Onay iste" modunu seçen kullanıcının değerli eşyası, cevap vermediği için harcanabiliyor. | Zaman aşımı **yeni yetki vermez**: riskli adım atlanır, alternatif seçilir veya görev güvenle sonlandırılır (§5.7). |
| 12 | **Belge hataları:** §5.7'de eski tablo kalıntısı ve iki "Ölçüm" tanımı; MineCollab "%15'e kadar" (doğrusu "%15'e varan düşüş"); SIMA 2 %31→%65 Minecraft'a özgü değil; Work2Skill "test edilmiyor" yanlış; Blocks.ai'de fazı **motor verisi** seçiyor (§6.2 yanlış aktarmıştı); L1 gecikme bütçesi tutarsız (300/500 ms, 2–10/5 Hz); Signed Rescue Routing sonuçları henüz "TBD"; yol haritası sırası hatalı (AFK, iptal edilebilir primitive'lerden önce); §0'da "üç ana fikir" altında 8 madde. | Hepsi düzeltildi. Gecikme bütçesi tek yerde tanımlandı (§6.1). |

**Astra'nın ek tespitleri (doğrulandı):**
- **Malde'nin reposu bulundu:** [rmalde/minecraft-agent](https://github.com/rmalde/minecraft-agent). End portalı önceden doğrulanmış, köy ve obsidyenli sandıklar seed'de hazır, ejderha başının konumu sunucuya eklenen salt-okur bir **sensörle** okunuyor. Gösterdiği şey entegrasyon; öğrenmeyi veya L1'in nedensel katkısını göstermiyor (§2.5 düzeltildi).
- **Claude'un resmî yardım sayfası var:** sadece Mac Cowork; ~10 dk sınır; video/ses saklanmıyor, ekran görüntüleri tutuluyor. Resmî sayfada **takip soruları anlatılmıyor** (§4.1 düzeltildi).

**Opus'un ek tespitleri:**
- **Algı adaleti ("x-ray"):** Mineflayer yüklü chunk'ların tamamını görüyor; taşın içindeki elmas da bulunuyor. LLM kodu `bot.chat('/give …')` çağırabilir. → Bot op olmaz, senaryo kurulumu **sadece RCON** ile yapılır, LLM kodunda `/` komutları statik olarak yasak. Görünürlük modeli Fatih'e soru (§14.4).
- **Bayat eklentiler:** `mineflayer-pathfinder` 2.4.5 (2023-09), `mineflayer-pvp` 1.3.2 (2022-07), `mineflayer-tool` 1.2.0 (2022-05). `prismarine-viewer` 1.21.11'de 1.21.4 dokularına düşüyor. → İlk spike uyumluluk testi (S1).
- **Kayıt proxy'si zorlukları:** 1.20.2+ configuration fazı, imzalı sohbet (`enforce-secure-profile=false`), craft'ın iki yolu (recipe book paketi ve slot tıklamaları), istemci isteği ile sunucu onayının ayrışması.
- **Duvar saati bütçesi:** 6 ablasyon × 10 seed × 3 tekrar ≈ 180–360 saat. Uzun koşular az tutulmalı, ağırlık 2–10 dakikalık RCON senaryo görevlerinde olmalı.

### 14.3 Eksikler listesi (ikisinin birleşimi) → tasarıma eklenecek

| Eksik | Kısa çözüm yönü |
|---|---|
| Durum tutarlılığı | Snapshot sürümü, olay sıra numarası, kopan akışı tamamlama, `unknown` alanları |
| Yeniden başlatma uzlaştırması | Gönderildiği bilinen ama uygulandığı bilinmeyen eylem; tekrar gönderimde mükerrer etkiyi önleme (idempotens) |
| Yetki ayrımı | Değerlendiricinin `/give`, reset ve gerçek durum erişimi ajana kapalı (RCON sadece değerlendirici ve senaryo kurucuda) |
| Gözlemlenebilirlik | Ortak iz kimliği (L2 çağrısı → beceri → primitive → olay), kuyruk süresi, atılan bayat cevaplar, kesme gecikmesi, doğrulayıcı anlaşmazlığı, oturum tekrar oynatma |
| Test altyapısı | Sahte bot (primitive birim testleri), Docker MC ile senaryo koşucusu, deterministik test dünyası |
| Veri yaşam döngüsü | SQLite ↔ `.js` dosyası atomik yayın, beceri bağımlılık hash'leri, göçler, log saklama ve sıkıştırma |
| Sürümleme matrisi | Beceri ↔ primitive API ↔ prompt ↔ model ↔ MC sürümü (skill drift'in pratik karşılığı) |
| Güvenlik | vm/süreç bağlamına verilenler (`require`, `process`, ağ, `.env` yok). Sohbet, tabela ve kitap metni L1/L2 için **prompt injection kanalı** → durum verisi olarak işaretlenir, talimat sayılmaz. |
| İşletim | API kesintisi, PC uyuması/kapalıyken yedek yol, GPU bellek baskısı, eğitim ile servisin çakışması, disk sınırı |
| Kurs eşlemesi | "≥20 test, başarı, maliyet, gecikme, video" çıktılarının kilometre taşlarına bağlanması; demo için sabit bir "çekim seed'i" |
| Gözlem eylemleri | "Bilmiyorum" durumunda sandığı açmak / alanı incelemek meşru bir eylem; belirsizlik otomatik tahmine dönüşmesin (Astra) |
| `obtain` sınırları | Sonlu desteklenen eşya kümesi, döngü tespiti, kaynak rezervasyonu, açık `unsupported` / `unreachable` sonuçları (Astra) |
| Kayıtta anlam katmanları | İstek / sunucu onayı / gözlenen değişiklik / çıkarılan anlam ayrı tutulur; ham kayıt korunur; L1 temizleme geri alınabilir işaretlemedir (Astra) |

### 14.4 Fatih'in kararına bırakılanlar → verilen kararlar (2026-10-15)

| Konu | Karar |
|---|---|
| L2 kademesi | **Sonnet 5.5 varsayılan**, Haiku 5.5 metin işleri; kademe ve Opus S5'te ölçülür (§6.8) |
| Teslim kapsamı | **Hepsi kalsın**; risk sıralamayla yönetilir (§12) |
| Ana iddia | **Oynayarak öğrenme** (§11) |
| "Mükemmel" tanımı | **Kademeli**: elmas + 3 gün hayatta kalma + 25 görev ana; bilinmeyen dünyada Ender Dragon esnek (§11) |
| Algı adaleti | **İki mod**: adil (değerlendirme) + tam bilgi (AFK seçimi) (§11) |
| Kayıt sırası | **Aşamalı**: v1 blueprint + makro, v2 davranışsal (§4.6) |
| Mindcraft | **Parça ödünç al**, üstüne kurma (§5.5) |
| Teslim tarihi | Hâlâ açık |

İnceleyicilerin özgün görüşleri (kayıt için):

| Konu | İnceleyiciler ne diyor | Mevcut karar |
|---|---|---|
| **L2 kademesi** | İkisi de: kademenin faydası **tekil Sonnet tabanına karşı** kanıtlanmalı. Opus: bütçe kısıt değilse kademe sadece gecikme ve cache kaybı ekler; tek Sonnet ile başla, kademeyi deney kolu yap, Opus 5.5'i zor onarımda ölç. | KARAR #5: Haiku önce → Sonnet |
| **Teslim kapsamı** | İkisi de ertelemeyi öneriyor: kişilik/ruh hali (sadece günlük + öne çıkan anlar kalsın), ses komutu + görsel editör + zamanlama + telefon bildirimi, 6 L1 sağlayıcısının çoğu (teslimde kural + Jev + 1 yerel), fine-tune ve counterfactual (teslim sonrası veya kursun #42 projesi), 7 hafıza türünün çoğu (yer + sandık + kaynak durumu yeterli), `approver`/`consult` (önce `full` + `#dur`), Python SDK. | Vizyonda hepsi var |
| **Ana iddia** | Teslim tek ana iddia seçmeli: oynayarak öğrenme mi, gösterimden öğrenme mi, güvenilir AFK mı? | Belirsiz |
| **"Mükemmel" tanımı** | Sonlu bir görev kümesi olmalı: elmas kazma mı, Ender Dragon mu, yoldaş davranışı mı? | §11 taslak |
| **Algı adaleti** | Bot taşın içini görebilir mi, yoksa insana yakın bir görünürlük sınırı mı? | Tanımsız |
| **Kayıt v1 kapsamı** | Opus: v1 = deterministik blueprint + isimli alt hedef makrosu; davranışsal beceriler (tarım, savaş) v2. Astra: tek beceri ailesiyle başla. | §4.6 tam hat |
| **Mindcraft üstüne kurmak** | Opus: M0–M2 haftalardan günlere iner; bizim katkımız (sözleşmeli kütüphane, doğrulama, kayıt) onun üstüne gelir. Lisansı ve kod kalitesi kontrol edilmeli. | Sıfırdan |
| **Teslim tarihi ve haftalık süre** | İkisi de ilk soru olarak bunu soruyor; bütün kapsam kararları buna bağlı. | Açık |

### 14.5 Benimsenen alternatif fikirler (tasarıma girdi)

1. **Test-önce beceri sentezi:** önce yüklem + senaryo, sonra kod (14.2 #4).
2. **Beceri dili TypeScript + `tsc` tip kontrolü:** uydurma primitive ve yanlış argümanlar derlemede yakalanır. Haiku→Sonnet yükseltmesi için en ucuz nesnel tetikleyici (Opus).
3. **Sınırlı beceri dili önce:** Task IR / davranış ağacı beceri formatı olarak kullanılır; serbest kod sadece DSL'in ifade edemediği yaprak düğümlerde. Sandbox, kesme ve devam sorunlarının çoğu küçülür (iki model de önerdi).
4. **Gölge modda L1** (Astra) + **çevrimdışı karar benchmark'ı:** loglardan `(durum, karar, sonuç)` çıkarılır; sağlayıcılar oyun koşmadan karşılaştırılır (Opus).
5. **Aday beceri sürümü:** onarım çalışan beceriyi ezmez; aday regresyondan geçmeden etkinleşmez (Astra).
6. **Düzeltmeyle öğretme (DAgger tarzı):** bot dener, oyuncu `//` ile düzeltir ("hayır, önce meşale"); düzeltme kurala dönüşür. Tek gösterimden genellemekten daha ucuz (Opus).
7. **Gösterimden fark öğrenme:** hazır primitive'leri yeniden keşfetmek yerine gösterimin **yeni** sıra, koşul ve istisnalarını çıkar (Astra).
8. **Karşı örnek fabrikası:** beceriyi bozacak durumlar (eksik araç, engel, değişmiş hedef) otomatik üretilir (Astra).
9. **`/tick freeze` / `/tick step`** ile dondurulmuş senaryolar: karar kalitesi gecikmeden ayrı ölçülür. Mineflayer fiziğiyle uyumu önce spike'la denenmeli (Opus).
10. **Gece vardiyası (L3) Batch API ile:** açıklama, regresyon onarım önerileri, öğretmen etiketleri toplu ve %50 indirimli (Opus).

### 14.6 Kod aşamasının ilk deneyleri (iki önerinin birleşimi)

Kod aşamasına geçilince **M0'dan önce** koşulacak spike'lar. Her biri en riskli bir varsayımı en ucuza test ediyor:

| # | Hipotez | Deney | Başarı ölçütü | Süre |
|---|---|---|---|---|
| S1 | MC 1.21.11 + mineflayer 4.39 + pathfinder/collectblock/pvp/tool + viewer yamasız çalışır | Docker itzg; bot 100 blok gider, ağaç keser, masa + kazma yapar, zombi öldürür, sandık kullanır; 10 koşu | 10/10 hatasız; viewer 1.21.11 bloklarını gösterir. Aksi halde sürüm/fork kararı | 1 gün |
| S2 | Ayrı süreç + watchdog kötü kodu ≤2 sn'de keser, eski iş eylem gönderemez | 20 hatalı beceri (senkron döngü, `await`'li sonsuz döngü, unhandled rejection, 5 dk pathfind, `process.exit`); `vm` ile ayrı süreç karşılaştırması; işlem ortasında kesme ve kopma | Ayrı süreçte %100 kesme ≤2 sn; ana süreç sağlam; kesme onayından sonra eski iş eylem gönderemiyor | 2 gün |
| S3 | Doğrulayıcı bağımsız ve reset tekrarlanabilir | 3 görev için doğru/yanlış son durumlar + 20 reset | Negatif örneklerde yanlış başarı = 0; başlangıç durumu alanları eşleşiyor | 1.5 gün |
| S4 | Jev, bağlamsal bir kararda L0 kuralını anlamlı geçer ve p95 ≤300 ms | RCON ile 200 senaryo; kural vs Jev vs Haiku (+1 yerel aday); seçenek sırası karıştırılmış 2 sorgu; etiket ile politika sonucu ayrı | Jev ≥ kural +5 puan (McNemar p<0.05) **ve** p95 ≤300 ms. Değilse L1 sadece dil-anlamsal noktalarda kalır | 3 gün |
| S5 | Kod yazmada kademe tekil Sonnet'e karşı değer katar | 10 görevlik dikey dilim (odun → taş kazma → fırın → demir); Haiku / Sonnet / Opus tekil + kademe, 5 tekrar; deneme sayısı, duvar saati, $ | Kademe başarıda Sonnet'ten belirgin düşük değil **ve** süre veya $'da belirgin iyi; değilse varsayılan Sonnet | 3 gün |
| S6 | Vanilla client proxy üzerinden kararlı oynar, olaylar doğru çıkarılır | 10 dk oyun; kır/yerleştir/craft/`//` olayları sunucu tarafı blok farkıyla çapraz kontrol; 3×3 sığınak blueprint'i taze dünyada yeniden kurulur | Kopma yok; olayların ≥%95'i doğru; blueprint 5/5 tekrarda ≥%95 blok isabeti | 2–3 gün |
| S7 | Öğrenilmiş tek bir bileşik beceri görülmemiş dünyada kazanç sağlar | Dondurulmuş çekirdek vs çekirdek + öğrenilmiş beceri; ayrı test seed'leri | Başarı düşmeden süre ve L2 çağrısı azalıyor; beceri gerçekten çağrılıyor | 2 gün |
| S8 | Eklenti sözleşmesi ikinci bir oyuna oturuyor | ViZDoom (Python) için sadece `handshake/observe/act/reset` | 1 günde çalışıyor; sözleşmede gereken değişiklik listesi çıkıyor | 1 gün |

---

## Kaynaklar

**Minecraft ajanları:** [Voyager makale](https://arxiv.org/abs/2305.16291) · [Voyager repo](https://github.com/MineDojo/Voyager) · [Mindcraft](https://github.com/mindcraft-bots/mindcraft) · [MineCollab](https://arxiv.org/abs/2504.17950) · [ODYSSEY](https://arxiv.org/abs/2407.15325) · [MindForge](https://arxiv.org/abs/2411.12977) · [MineEvolve](https://arxiv.org/abs/2603.13131) · [Programmatic Skill Networks](https://arxiv.org/abs/2601.03509) · [Project Sid](https://arxiv.org/abs/2411.00114) · [GITM](https://arxiv.org/abs/2305.17144) · [JARVIS-1](https://arxiv.org/abs/2311.05997) · [Optimus-1](https://arxiv.org/abs/2408.03615) · [MineNPC-Task](https://arxiv.org/abs/2601.05215) · [MineExplorer](https://arxiv.org/abs/2605.30931) · [PillagerBench](https://arxiv.org/abs/2509.06235) · [minecraft-mcp-server](https://github.com/yuniko-software/minecraft-mcp-server) · [Player2NPC](https://modrinth.com/mod/player2npc) · [Mineflayer](https://github.com/PrismarineJS/mineflayer) · [node-minecraft-protocol](https://github.com/PrismarineJS/node-minecraft-protocol)

**Beceri kütüphaneleri:** [Skill drift](https://arxiv.org/abs/2605.10990) · [SkillsBench](https://arxiv.org/abs/2602.12670) · [Skills in the wild](https://arxiv.org/abs/2604.04323)

**Jev / System One:** [The Register](https://www.theregister.com/ai-and-ml/2026/09/16/typesafe-ai-debuts-model-for-machines-that-plays-doom/5296711) · [DataCamp](https://www.datacamp.com/blog/system-one-models-jev) · [LumaDock](https://lumadock.com/blog/what-is-jev-typesafe) · [Medium](https://medium.com/@creativeaininja/typesafes-jev-makes-ai-decisions-fast-enough-to-play-doom-68fdcce1159a) · [jev-plays-doom](https://github.com/tirukovelamanoj/jev-plays-doom) · [Blocks.ai replika](https://blocks.ai/blog/jev-open-model-doom) · [TypeSafe docs](https://docs.typesafe.ai/llms.txt) · [models](https://docs.typesafe.ai/models.md) · [jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md) · [images](https://docs.typesafe.ai/images.md) · [skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion.md)

**Genel oyun ajanları:** [SIMA 2](https://arxiv.org/abs/2512.04797) · [Cradle](https://arxiv.org/abs/2403.03186) · [Lumine](https://arxiv.org/abs/2511.08892) · [NitroGen](https://arxiv.org/abs/2601.02427) · [Game-TARS](https://arxiv.org/abs/2510.23691) · [SpeedrunBench](https://arxiv.org/abs/2610.08076) · [AI for Games survey](https://arxiv.org/abs/2609.16679) · [LLM game agent survey](https://github.com/git-disl/awesome-LLM-game-agent-papers)

**Record a skill:** [Codex Record & Replay resmî doküman](https://learn.chatgpt.com/docs/extend/record-and-replay) · [Codex uygulamalı deneme](https://azukiazusa.dev/en/blog/workflow-to-reusable-skill/) · [Codex denetim listesi](https://chatgptaihub.com/audit-repair-codex-record-replay-skill) · [kingy.ai](https://kingy.ai/news/codex-record-and-replay/) · [Claude: leadwithai](https://www.leadwithai.co/article/record-a-skill-claude-cowork) · [Claude: The Decoder](https://the-decoder.com/claude-cowork-learns-new-skills-through-screen-recordings-and-voice-over-explanations/) · [Claude: AI Weekly](https://aiweekly.co/alerts/anthropic-ships-record-a-skill-in-claude-cowork-desktop-app) · [Claude: remio eleştirisi](https://www.remio.ai/post/claude-cowork-skill-recording-turns-demonstrations-into-reusable-workflows-but-t) · [Claude Record a Skill](https://www.digitalapplied.com/blog/claude-record-a-skill-train-agents-by-demonstration-2026) · [Codex Record & Replay](https://webiano.digital/record-and-replay-turns-a-single-demo-into-a-reusable-codex-skill/) · [Microsoft Skill Recorder](https://themenonlab.blog/blog/microsoft-skill-recorder-teach-agents-by-demonstration) · [Work2Skill](https://arxiv.org/abs/2610.12984) · [Hierarchical demonstrations](https://arxiv.org/abs/2606.20978) · [Skill-Pro](https://arxiv.org/abs/2602.01869)

**System 1 alternatifleri:** [Unsloth karar modeli](https://unsloth.ai/docs/new/train-your-own-decision-model-with-unsloth) · [AlphaSignal özeti](https://alphasignal.ai/news/unsloth-turns-a-0-8b-model-into-a-fast-decision-engine-at-78-accuracy) · [GLiClass](https://arxiv.org/abs/2508.07662) · [BTZSC](https://arxiv.org/abs/2603.11991) · [Encoder vs LLM maliyet](https://arxiv.org/abs/2602.06370) · [LLM vs fine-tune NLU](https://arxiv.org/abs/2608.20371) · [Agent distillation](https://arxiv.org/abs/2505.17612) · [TypeSafe self-consistency](https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook.md) · [TypeSafe confidence routing](https://docs.typesafe.ai/patterns/confidence-routing.md)

**Hafıza ve kademe:** [MrSteve](https://arxiv.org/abs/2411.06736) · [EmbodiedMemory-Bench](https://arxiv.org/abs/2609.28236) · [Remember the Decision](https://arxiv.org/abs/2605.10870) · [Agent memory survey](https://arxiv.org/abs/2603.07670) · [Signed Rescue Routing](https://arxiv.org/abs/2609.07786) · [Cascade routing ICML 2025](https://icml.cc/virtual/2025/poster/46183) · [Routing/cascading survey](https://arxiv.org/abs/2603.04445) · [Mindcraft hafıza prompt'u](https://huggingface.co/Sweaterdog/Andy-3.5/commit/fa0af5152a96579ab40fe5d8900a7d7a26f2ab62)

**Beceri tasarımı, pipeline ve kişilik:** [SkillsBench](https://arxiv.org/abs/2602.12670) · [Generative skill composition](https://arxiv.org/abs/2606.32025) · [AgentSkillOS](https://arxiv.org/abs/2603.02176) · [SkillEval](https://arxiv.org/abs/2608.06891) · [NVIDIA SkillEvaluator](https://developer.nvidia.com/blog/evaluating-ai-agent-skill-performance-with-nvidia-skillevaluator/) · [SoK: Agentic Skills](https://arxiv.org/html/2602.20867) · [Baritone](https://git.psf.lt/0xf8/baritone/raw/branch/1.12.2/USAGE.md) · [AIBot Bob](https://p.codekk.com/detail/6a033e245b02fc5c75bba05c) · [nekostulAICompanion](https://moddex.gg/mod/nekostulaicompanion) · [LLM→behavior tree](https://arxiv.org/abs/2302.12927) · [Wingman AI](https://ai.google.dev/competition/projects/wingman-ai) · [GPT-6 Astra: Dexerto](https://www.dexerto.com/minecraft/gpt-6-astra-forced-to-play-minecraft-gets-depressed-by-creeper-and-farms-potatoes-for-hours-3409634/) · [Tom's Hardware](https://www.tomshardware.com/tech-industry/artificial-intelligence/defeated-gpt-6-astra-model-spent-several-hours-just-farming-potatoes-after-being-blown-up-by-a-creeper-in-minecraft-openai-offering-gets-further-than-any-other-ai-system-in-141-hour-test) · [XDA](https://www.xda-developers.com/gpt-6-astra-made-amazing-progress-on-minecraft-until-a-creeper-blew-up-its-chest-and-it-spiralled-into-sadness/) · [Yahoo](https://www.yahoo.com/entertainment/articles/gpt-6-astra-plays-minecraft-224156819.html) · [Ender Dragon: ASCII.jp](https://ascii.jp/en/elem/000/004/436/4436545/) · [Vals CUA-Bench özeti](https://hermes-ai.net/news/vals-ai-s-cua-bench-humbles-every-frontier-agent-below-20-points/) · [Project Sid: MIT TR](https://www.technologyreview.com/2024/11/27/1107377/a-minecraft-town-of-ai-characters-made-friends-invented-jobs-and-spread-religion/amp/) · [MIMIC](https://arxiv.org/html/2510.01635v1)

**Otonomi ve eklenti mimarisi:** [Levels of Autonomy for AI Agents](https://arxiv.org/abs/2506.12469) · [Knight Columbia özeti](https://knightcolumbia.org/content/levels-of-autonomy-for-ai-agents-1) · [Human out of the loop](https://concepts.dsebastien.net/concept/human-out-of-the-loop/) · [HF: tam otonom ajanlara karşı](https://aiweekly.co/node/9510) · [IEEE Spectrum: onay süreçleri](https://spectrum.ieee.org/agentic-ai-humans-in-loop) · [General Modular Harness for game agents](https://arxiv.org/abs/2507.11633)

**Dış inceleme:** [Opus raporu](reviews/2026-10-15-opus.md) · [GPT-6-Astra raporu](reviews/2026-10-15-astra.md) · [rmalde/minecraft-agent](https://github.com/rmalde/minecraft-agent) · [Claude Record a skill resmî](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills) · [Node vm zaman aşımı](https://nodejs.org/docs/latest-v22.x/api/vm.html#timeout-interactions-with-asynchronous-tasks-and-promises) · [mineflayer-pathfinder stop](https://github.com/PrismarineJS/mineflayer-pathfinder#botpathfinderstop) · [Unsloth Laya servis](https://unsloth.ai/docs/models/decision-laya)
