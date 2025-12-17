#!/bin/bash
# Security Check Script for Juniper Container Backup
# Verifies that sensitive files are properly protected

set -e

echo "🔍 Verificando segurança do repositório..."
echo ""

ERRORS=0
WARNINGS=0

# Check 1: Verify .gitignore exists
if [ ! -f .gitignore ]; then
    echo "❌ ERRO: .gitignore não encontrado!"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ .gitignore encontrado"
fi

# Check 2: Verify sensitive files are in .gitignore
echo ""
echo "📋 Verificando arquivos sensíveis no .gitignore..."

SENSITIVE_FILES=(".env" "inventory.yaml" "backups/" "*.log")
for file in "${SENSITIVE_FILES[@]}"; do
    if grep -q "^${file}$" .gitignore 2>/dev/null; then
        echo "  ✅ $file está no .gitignore"
    else
        echo "  ❌ $file NÃO está no .gitignore"
        ERRORS=$((ERRORS + 1))
    fi
done

# Check 3: Verify sensitive files are NOT in Git
echo ""
echo "📂 Verificando se arquivos sensíveis foram commitados..."

if git ls-files | grep -qE "(^\.env$|^inventory\.yaml$)"; then
    echo "  ❌ CRÍTICO: Arquivos sensíveis foram commitados ao Git!"
    git ls-files | grep -E "(^\.env$|^inventory\.yaml$)" | while read file; do
        echo "     - $file"
    done
    ERRORS=$((ERRORS + 1))
else
    echo "  ✅ Nenhum arquivo sensível no repositório Git"
fi

# Check 4: Verify file permissions (if files exist)
echo ""
echo "🔐 Verificando permissões de arquivos..."

check_permissions() {
    local file=$1
    local expected=$2
    
    if [ -f "$file" ]; then
        if [ "$(uname)" = "Darwin" ]; then
            # macOS
            PERM=$(stat -f %A "$file")
        else
            # Linux
            PERM=$(stat -c %a "$file")
        fi
        
        if [ "$PERM" = "$expected" ]; then
            echo "  ✅ $file: $PERM (correto)"
        else
            echo "  ⚠️  $file: $PERM (recomendado: $expected)"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        echo "  ℹ️  $file: não existe (OK)"
    fi
}

check_permissions ".env" "600"
check_permissions "inventory.yaml" "600"

# Check 5: Verify example files exist
echo ""
echo "📄 Verificando arquivos de exemplo..."

EXAMPLE_FILES=(".env.example" "inventory.example.yaml")
for file in "${EXAMPLE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file existe"
    else
        echo "  ⚠️  $file não encontrado"
        WARNINGS=$((WARNINGS + 1))
    fi
done

# Check 6: Search for potential secrets in code
echo ""
echo "🔎 Procurando por possíveis credenciais hardcoded..."

FOUND_SECRETS=0
if git grep -niE "(password|secret|token|api_key)\s*=\s*['\"][^'\"]{8,}" -- '*.py' '*.yml' '*.yaml' 2>/dev/null | grep -v ".example" | grep -v "# Example" | grep -v "your_"; then
    echo "  ⚠️  Possíveis credenciais encontradas no código!"
    WARNINGS=$((WARNINGS + 1))
    FOUND_SECRETS=1
fi

if [ $FOUND_SECRETS -eq 0 ]; then
    echo "  ✅ Nenhuma credencial hardcoded detectada"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 RESUMO DA VERIFICAÇÃO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "✅ Todos os checks passaram!"
    echo ""
    echo "🔒 Seu repositório está seguro para commit."
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo "⚠️  $WARNINGS avisos encontrados"
    echo ""
    echo "Avisos não impedem o commit, mas devem ser revisados."
    exit 0
else
    echo "❌ $ERRORS erros encontrados"
    if [ $WARNINGS -gt 0 ]; then
        echo "⚠️  $WARNINGS avisos encontrados"
    fi
    echo ""
    echo "🚨 CORRIJA OS ERROS ANTES DE FAZER COMMIT!"
    echo ""
    echo "Para mais informações, consulte: SECURITY.md"
    exit 1
fi
