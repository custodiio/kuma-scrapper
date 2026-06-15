# 🍪 Como obter o Cookie do Douyin

O cookie é necessário para que a API do Evil0ctal consiga fazer requisições ao Douyin sem ser bloqueada.

## Passo a passo

### 1. Acesse o Douyin no navegador

Abra o Chrome e acesse: **https://www.douyin.com**

> ⚠️ Pode ser necessário usar VPN chinesa ou proxy se estiver fora da China.

### 2. Faça login (opcional mas recomendado)

O login aumenta o limite de requisições e melhora os resultados de busca.
- Use um número de telefone chinês, ou
- Use login via WeChat/QQ

### 3. Abra as DevTools

1. Pressione **F12** (ou Ctrl+Shift+I)
2. Vá para a aba **Network** (Rede)
3. Recarregue a página (**F5**)

### 4. Copie o Cookie

1. Clique em qualquer requisição na lista (de preferência uma para `www.douyin.com`)
2. Na aba **Headers**, role até encontrar **Cookie**
3. Clique com botão direito no valor e selecione **Copy value**

### 5. Cole no .env

```bash
DOUYIN_COOKIE=ttwid=xxx; msToken=xxx; odin_tt=xxx; sessionid=xxx; ...
```

> ⚠️ Cole o cookie inteiro numa única linha, sem quebras.

## Cookies importantes

| Cookie | Descrição |
|--------|-----------|
| `ttwid` | Cookie de segurança principal |
| `msToken` | Token de verificação (muda frequentemente) |
| `odin_tt` | Tracking de dispositivo |
| `sessionid` | Sessão do usuário logado |

## Renovação

- O cookie expira em **~30 dias**
- Quando o scraper retornar **0 resultados**, é hora de renovar
- Repita o processo acima e atualize o `.env`

## Dicas

- Use o Chrome em modo normal (não incógnito) para manter a sessão
- Não limpe os cookies do Douyin após copiá-los
- Se possível, mantenha a sessão ativa acessando o site ocasionalmente
