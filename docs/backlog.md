# Backlog — yarım kalan işler

Agentlar bir oturumu bitirirken **tamamlanmamış** her işi buraya yazar. Bir sonraki agent işe buradan başlar.
Planlanan ama hiç başlanmamış işler buraya değil, `research.md` §12 yol haritasına aittir.

## Kurallar

- Her madde tek bir iş. En yeni madde **Açık** bölümünün en üstüne.
- İş bitince maddeyi silme: **Kapanan** bölümüne taşı, kapanış tarihini ve kanıtı (commit, test çıktısı) ekle.
- Bir madde büyürse (alt işleri, ayrıntılı notları, çok adımlı planı varsa) `docs/backlog/<konu>.md` adında
  **alt-backlog** dosyası aç ve maddeden ona bağlantı ver. Alt-backlog da aynı formatı kullanır;
  o da büyürse `docs/backlog/<konu>/<alt-konu>.md` diye derinleşebilir.
- Yarım bırakırken "neredeydim" bilgisini net yaz: hangi dosya, hangi adım, neyin doğrulanmadığı.

## Madde formatı

```markdown
### [M2] Kısa başlık
- **Durum**: yarım | engelli | inceleme bekliyor
- **Açan**: <agent veya Fatih> · **Tarih**: YYYY-AA-GG
- **Ne yapıldı**: ...
- **Kalan**: ...
- **Neredeydim**: dosya/fonksiyon, son çalıştırılan komut
- **Engel / bilinmeyen**: (varsa)
- **Alt-backlog**: [docs/backlog/<konu>.md](backlog/<konu>.md) (varsa)
```

`[M0]`…`[M9]` etiketi research.md §12 yol haritasındaki kilometre taşını gösterir.

---

## Açık

_Henüz yarım kalan iş yok. Kod yazımı başlamadı; Fatih'in `notes.md` → "Açık sorular"a cevabı bekleniyor._

---

## Kapanan

- **2026-10-15 · claude-code** — Araştırma ve dokümantasyon iskeleti: `docs/research.md`, `AGENTS.md` (+ `CLAUDE.md` sembolik bağı), `docs/notes.md`, `docs/backlog.md`.
