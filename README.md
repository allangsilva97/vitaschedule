# VitaSchedule

Protótipo de sistema de agendamento e gestão de pacientes para clínicas: um único arquivo HTML, sem servidor.

> **Aviso:** é uma demonstração que roda 100% no navegador, com dados fictícios. Login, perfis e regras
> de acesso existem só no lado do cliente e **não protegem dados reais**. Não use com informações de
> pacientes de verdade. Veja [SECURITY.md](SECURITY.md).

## O que tem

- **Paciente:** agenda consultas, cancela as próprias e acompanha o status.
- **Recepção:** agenda presencialmente, atualiza status e vê a agenda de todos os profissionais.
- **Médico(a):** vê só os próprios pacientes e prontuários e bloqueia a própria agenda.
- **Administrador:** gerencia usuários, vê a auditoria e o status de conformidade.
- **Consulta pública de status:** exige protocolo **e** CPF, e devolve apenas dados mínimos.
- Tema claro/escuro e interface responsiva.

## Como rodar

Abra o `index.html` no navegador (duplo clique). Não precisa instalar nada.
Os ícones (Font Awesome) e a fonte (Google Fonts) vêm da internet; sem conexão a página funciona, só sem eles.

Na tela de login (botão **Entrar**) há um seletor de perfil que preenche o e-mail da conta de demonstração e
mostra a senha de demonstração. As contas são:

| Perfil | E-mail |
| --- | --- |
| Paciente | `paciente@vitamed.com` |
| Recepção | `recepcao@vitamed.com` |
| Médica | `mariana.souza@vitamed.com` |
| Administrador | `admin@vitamed.com` |

Para desligar a caixa de demonstração, mude `DEMO_MODE` para `false` no início do script e rode o build
(veja [Desenvolvimento](#desenvolvimento)), porque o script tem hash na CSP.

## Estrutura

```
index.html      aplicação completa (HTML + CSS compilado + JavaScript)
build/          ferramenta de build (Tailwind + hashes da CSP)
_headers        cabeçalhos de segurança para Netlify / Cloudflare Pages
SECURITY.md     modelo de segurança, limites e checklist para produção
```

## Desenvolvimento

O CSS do Tailwind é compilado e embutido no `index.html`, e a Content-Security-Policy libera o script e o
CSS **por hash** (sem `unsafe-inline`). Por isso, depois de editar o `index.html` (classes do Tailwind ou o
`<script>`), rode o build para recompilar o CSS e atualizar os hashes; sem isso o navegador bloqueia o que mudou.

```bash
cd build
npm ci --ignore-scripts   # só na primeira vez (Tailwind 3.4.17 fixado no package-lock.json)
npm run build
```

Não edite à mão o bloco `<style>` nem os hashes da CSP: eles são regenerados a cada build.

## Hospedagem

- **GitHub Pages:** funciona, mas não aceita cabeçalhos HTTP personalizados. O código anti-iframe do
  próprio `index.html` cobre o clickjacking nesse caso.
- **Netlify / Cloudflare Pages:** o arquivo `_headers` já aplica `frame-ancestors`, `nosniff`, HSTS e outros.
- Sempre sirva por **HTTPS**.
