# 🔍 Termos de Busca — Douyin Anime Scraper

Lista de termos de busca recomendados em chinês para encontrar conteúdo de anime no Douyin.

## Termo principal (configurado no .env)

```
新番解说
```

**Tradução:** "Comentário/Recap de novos animes"

## Termos alternativos

### Recaps e Resumos
| Chinês | Pinyin | Significado |
|--------|--------|-------------|
| `新番解说` | xīn fān jiěshuō | Recap de novos animes |
| `动漫解说` | dòngmàn jiěshuō | Comentário de anime |
| `动画解说` | dònghuà jiěshuō | Comentário de animação |
| `番剧解说` | fān jù jiěshuō | Recap de séries anime |
| `本周新番` | běn zhōu xīn fān | Novos animes da semana |

### Por gênero
| Chinês | Pinyin | Significado |
|--------|--------|-------------|
| `热血动漫` | rè xuè dòngmàn | Anime de ação/shounen |
| `后宫动漫` | hòugōng dòngmàn | Anime harem |
| `异世界动漫` | yì shìjiè dòngmàn | Anime isekai |
| `恋爱动漫` | liàn'ài dòngmàn | Anime romance |

### Formatos populares
| Chinês | Pinyin | Significado |
|--------|--------|-------------|
| `动漫推荐` | dòngmàn tuījiàn | Recomendação de anime |
| `动漫混剪` | dòngmàn hùn jiǎn | AMV / edits de anime |
| `动漫名场面` | dòngmàn míng chǎng miàn | Cenas icônicas de anime |

### Por anime específico (exemplos)
| Chinês | Anime |
|--------|-------|
| `海贼王解说` | One Piece recap |
| `咒术回战解说` | Jujutsu Kaisen recap |
| `鬼灭之刃解说` | Demon Slayer recap |
| `进击的巨人解说` | Attack on Titan recap |
| `我的英雄学院` | My Hero Academia |
| `间谍过家家` | Spy x Family |
| `葬送的芙莉莲` | Frieren |
| `药屋少女的呢喃` | Kusuriya no Hitorigoto |

## Como usar múltiplos termos

Atualmente o scraper busca **1 termo por execução** (definido em `SEARCH_TERM`).

Para buscar múltiplos termos, você pode:
1. Alterar o `SEARCH_TERM` no `.env` periodicamente
2. Futuramente: implementar busca com lista de termos separados por `|`

## Dicas

- Termos com `解说` (jiěshuō = comentário/recap) retornam vídeos mais longos e explicativos
- Termos com `混剪` (hùn jiǎn = edição/AMV) retornam vídeos mais curtos (bom para Shorts)
- Adicionar o nome do anime específico + `解说` é o melhor para encontrar recaps de uma série
