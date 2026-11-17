# Segurança

## Arquitetura de segurança

Autenticação, autorização, validação, limite de tentativas e auditoria rodam **no servidor** (`api/`). O front só
exibe o que a API devolve; esconder botões é conveniência de UI, não controle de acesso. A sessão é um JWT em cookie
`HttpOnly; Secure; SameSite=Strict` (15 min deslizantes); mutações exigem o cabeçalho `X-Requested-With`; senhas usam
scrypt; horários duplos são barrados por índice único no banco. A API serve o `index.html` na mesma origem
(`connect-src 'self'`).

**Limites atuais:** o limitador de tentativas é em memória (vale por instância); 2FA ainda é só um campo; e-mails de
confirmação/lembrete e redefinição de senha **não são enviados** (apenas registrados); criptografia em repouso depende do
provedor do banco. Os dados semeados com `SEED_DEMO=true` são fictícios e a senha de demonstração é pública.

## O que o código já faz

- **Sem XSS:** todo texto vindo de formulário é escapado (`esc()`) ou inserido por `textContent`; não há
  `eval`, `document.write` nem handlers inline (`onclick=`); os eventos usam `data-action` com delegação.
  Revisadas as 133 interpolações de template do script: as que vão para HTML passam por `esc()` ou são
  números e constantes.
- **CSP rígida** (via `<meta>`): `default-src 'none'`; scripts e estilos liberados só por hash SHA-256;
  sem `unsafe-inline` nem `unsafe-eval`; `connect-src 'none'`; `form-action 'none'`; `base-uri 'none'`;
  `object-src 'none'`. Nenhum script de terceiros (o Tailwind é compilado, não carregado de CDN).
- **SRI** no CSS do Font Awesome; `Referrer-Policy: no-referrer` via `<meta>`.
- **Anti-clickjacking de reserva:** se a página for aberta dentro de um `<iframe>`, ela não renderiza nada.
- **Login de demonstração:** senhas com PBKDF2-SHA256 (100 mil iterações, salt por usuário), comparação em
  tempo constante, mensagem genérica de erro, limite de tentativas e logout por inatividade (15 min).
- **Controle de acesso no cliente (RBAC):** cada perfil só abre as próprias telas; médico vê só os próprios
  pacientes; paciente cancela só as próprias consultas; o último administrador não pode ser removido.
- **Validações:** CPF com dígitos verificadores, datas, horários e convênios em lista fixa, anti-duplicidade
  de horário, protocolo aleatório (`crypto.getRandomValues`).
- **LGPD (o que dá para fazer sem servidor):** CPF e nome mascarados, consentimento registrado, consulta
  pública exige protocolo + CPF, trilha de auditoria sem dados digitados pelo usuário.

## O que NÃO está resolvido (precisa de backend)

| Ponto | Por quê |
| --- | --- |
| Autenticação e autorização reais | Hoje rodam no navegador e podem ser contornadas pelo DevTools. |
| Limite de tentativas / anti-força-bruta | O limitador atual vive na aba; recarregar a página zera. |
| Criptografia e persistência dos dados | Nada é gravado; em produção, criptografia em trânsito e em repouso. |
| Auditoria imutável | O log atual é em memória. |
| 2FA | A coluna "2FA" é só visual. |
| Google Fonts | A fonte é carregada do Google, que recebe o IP do visitante. Para LGPD estrita, hospede a Inter localmente. |
| `frame-ancestors`, `X-Frame-Options`, `nosniff`, HSTS | Só funcionam como cabeçalho HTTP (veja `_headers`); o GitHub Pages não permite. |

## Checklist antes de usar com dados reais

1. Mover login, perfis e dados para um servidor, com sessão em cookie `HttpOnly; Secure; SameSite`.
2. Checar a permissão de **cada requisição** no servidor, nunca só esconder botões.
3. Limitar tentativas por IP/conta no servidor e ativar 2FA de verdade.
4. Criptografar o banco, fazer backup e manter log de auditoria imutável.
5. Definir `DEMO_MODE = false` e remover as contas e senhas de demonstração.
6. Enviar os cabeçalhos HTTP do `_headers` e servir só por HTTPS.
7. Hospedar fontes e ícones localmente e revisar a base legal e o consentimento (LGPD).

## Dependências

Só o build usa dependências (Tailwind 3.4.17, fixado no `package-lock.json`, com integridade conferida).
Instale com `npm ci --ignore-scripts`. O `npm audit` não encontrou vulnerabilidades em 14/11/2026.
O `index.html` publicado não carrega nenhum pacote npm.

## Como reportar uma vulnerabilidade

Use a aba **Security** do repositório no GitHub (*Report a vulnerability*). Se ela não estiver disponível,
abra uma issue pedindo contato, sem colocar detalhes da falha em público.
