# 🔒 Guia de Segurança - Juniper Container Backup

## ⚠️ Informações Sensíveis Protegidas

Este projeto está configurado para **NUNCA** versionar informações sensíveis no Git.

### Arquivos Protegidos pelo .gitignore

#### 🔐 Credenciais
- ✅ `.env` - Variáveis de ambiente (senhas, tokens)
- ✅ `inventory.yaml` - IPs, usuários e senhas dos dispositivos
- ✅ `credentials.*` - Qualquer arquivo de credenciais
- ✅ `secrets.*` - Arquivos de secrets
- ✅ `*.key`, `*.pem`, `*.crt` - Chaves SSH e certificados

#### 📊 Dados Sensíveis
- ✅ `backups/` - Configurações dos dispositivos (podem conter IPs internos)
- ✅ `*.log` - Logs (podem conter IPs e detalhes de erros)
- ✅ Arquivos de teste com credenciais

## 📋 Checklist de Segurança

### Antes de Fazer Commit

```bash
# 1. Verificar status do Git
git status

# 2. Verificar se arquivos sensíveis estão sendo ignorados
git check-ignore .env inventory.yaml backups/

# 3. Verificar o que será commitado
git diff --cached

# 4. NUNCA force add arquivos ignorados
# ❌ NÃO FAÇA: git add -f .env
# ❌ NÃO FAÇA: git add -f inventory.yaml
```

### Configuração Inicial

```bash
# 1. Copiar arquivos de exemplo
cp .env.example .env
cp inventory.example.yaml inventory.yaml

# 2. Configurar permissões restritas
chmod 600 .env
chmod 600 inventory.yaml

# 3. Editar com suas credenciais
nano .env
nano inventory.yaml

# 4. Verificar que estão ignorados
git status  # .env e inventory.yaml NÃO devem aparecer
```

## 🚨 Se Você Acidentalmente Commitou Dados Sensíveis

### Opção 1: Remover do Último Commit (se ainda não fez push)

```bash
# Remover arquivo do commit
git rm --cached .env
git rm --cached inventory.yaml

# Fazer novo commit
git commit --amend -m "Remove sensitive files"
```

### Opção 2: Remover do Histórico (se já fez push)

```bash
# CUIDADO: Reescreve o histórico do Git
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env inventory.yaml" \
  --prune-empty --tag-name-filter cat -- --all

# Force push (coordene com a equipe!)
git push origin --force --all
```

### Opção 3: Usar BFG Repo-Cleaner (recomendado para repositórios grandes)

```bash
# Instalar BFG
# https://rtyley.github.io/bfg-repo-cleaner/

# Remover arquivos sensíveis
bfg --delete-files .env
bfg --delete-files inventory.yaml

# Limpar histórico
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# Force push
git push origin --force --all
```

### Opção 4: Trocar TODAS as Credenciais (CRÍTICO!)

Se você commitou credenciais:

1. ✅ **Trocar IMEDIATAMENTE todas as senhas** dos dispositivos
2. ✅ **Revogar tokens** do Telegram Bot
3. ✅ **Auditar acessos** aos dispositivos
4. ✅ **Notificar equipe de segurança**
5. ✅ Limpar histórico do Git (opções acima)

## 🛡️ Boas Práticas de Segurança

### 1. Permissões de Arquivo

```bash
# Arquivos de configuração devem ser legíveis apenas pelo dono
chmod 600 .env
chmod 600 inventory.yaml

# Diretório de backups
chmod 700 backups/

# Verificar permissões
ls -la .env inventory.yaml
# Deve mostrar: -rw------- (600)
```

### 2. Variáveis de Ambiente

```bash
# Nunca exponha credenciais em comandos
# ❌ ERRADO:
docker run -e PASSWORD=secret123 ...

# ✅ CORRETO:
docker run --env-file .env ...
```

### 3. Secrets Management (Produção)

Para ambientes de produção, use soluções profissionais:

#### Docker Swarm
```yaml
secrets:
  juniper_password:
    external: true
```

#### Kubernetes
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: juniper-credentials
type: Opaque
data:
  username: YWRtaW4=  # base64 encoded
  password: c2VjcmV0  # base64 encoded
```

#### HashiCorp Vault
```bash
# Armazenar credenciais
vault kv put secret/juniper username=admin password=secret

# Recuperar no container
vault kv get -field=password secret/juniper
```

### 4. Auditoria Regular

```bash
# Verificar se .gitignore está funcionando
git ls-files | grep -E "(\.env|inventory\.yaml|\.log)"
# Não deve retornar nada!

# Verificar histórico por credenciais vazadas
git log -p | grep -i "password\|secret\|token"
```

## 📝 Arquivos Seguros para Versionar

Estes arquivos **PODEM** ser versionados (não contêm dados sensíveis):

- ✅ `.env.example` - Template sem credenciais reais
- ✅ `inventory.example.yaml` - Exemplo de configuração
- ✅ `README.md` - Documentação
- ✅ `Dockerfile` - Configuração do container
- ✅ `docker-compose.yml` - Orquestração
- ✅ `src/*.py` - Código fonte
- ✅ `.gitignore` - Regras de ignore

## 🔍 Verificação de Segurança

Execute este script para verificar a segurança do repositório:

```bash
#!/bin/bash
echo "🔍 Verificando segurança do repositório..."

# Verificar se arquivos sensíveis estão ignorados
if git check-ignore -q .env inventory.yaml; then
    echo "✅ Arquivos sensíveis estão no .gitignore"
else
    echo "❌ ERRO: Arquivos sensíveis NÃO estão ignorados!"
    exit 1
fi

# Verificar se arquivos sensíveis estão no Git
if git ls-files | grep -qE "(\.env$|inventory\.yaml$)"; then
    echo "❌ ERRO: Arquivos sensíveis foram commitados!"
    exit 1
else
    echo "✅ Nenhum arquivo sensível no repositório"
fi

# Verificar permissões
if [ -f .env ]; then
    PERM=$(stat -c %a .env 2>/dev/null || stat -f %A .env)
    if [ "$PERM" = "600" ]; then
        echo "✅ Permissões do .env corretas (600)"
    else
        echo "⚠️  Permissões do .env: $PERM (recomendado: 600)"
    fi
fi

echo "✅ Verificação concluída!"
```

## 📚 Recursos Adicionais

- [Git Security Best Practices](https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/Git_Cheat_Sheet.md)
- [Docker Secrets Documentation](https://docs.docker.com/engine/swarm/secrets/)
- [HashiCorp Vault](https://www.vaultproject.io/)
- [BFG Repo-Cleaner](https://rtyley.github.io/bfg-repo-cleaner/)

## ⚡ Resumo Rápido

```bash
# ✅ SEMPRE fazer
chmod 600 .env inventory.yaml
git status  # Verificar antes de commit
git diff --cached  # Revisar mudanças

# ❌ NUNCA fazer
git add -f .env
git add -f inventory.yaml
echo "PASSWORD=secret" >> .env && git add .env
```

---

**🔒 Lembre-se:** Segurança é responsabilidade de todos. Quando em dúvida, **NÃO COMMITE!**
