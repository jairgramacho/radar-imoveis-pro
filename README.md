# 🏠 Radar Imóveis - Marketplace de Compra, Venda e Aluguel

Um marketplace moderno e intuitivo para anunciar e buscar imóveis para compra, venda e aluguel. Os usuários podem entrar em contato direto com os anunciantes via WhatsApp.

## ✨ Funcionalidades

### 🔍 Busca com filtros inteligentes
- Filtros por tipo de negócio, tipo de imóvel, localização e preço
- Lista de imóveis com foto, preço, localização e principais atributos
- Visualização de detalhes completos do anúncio

### 📢 Publicação e gestão de anúncios
- Cadastro/login de usuários
- Publicação, edição e gerenciamento de anúncios próprios
- Upload e processamento de imagens (incluindo HEIC/HEIF)

### 🎯 Radar de Oportunidades
- Detecção de imóveis abaixo da média de comparáveis
- Critério de oportunidade por desconto percentual mínimo
- Exibição em aba dedicada para facilitar descoberta

### 💬 Comunicação e confiança
- Chat entre usuários autenticados
- Avaliação de experiência
- Páginas institucionais: termos, privacidade, denúncia de abuso e FAQ

### ⚙️ Conta do usuário
- Área de configurações de conta
- Atualização de nome, email, WhatsApp e senha

## 🛠️ Stack Tecnológico

- **Backend**: Flask (Python)
- **Frontend**: HTML5, Bootstrap 5, CSS3
- **Banco de Dados**: Arquivo de texto (porta para SQL em futuras versões)
- **Icons**: Font Awesome

## 📦 Instalação

### Pré-requisitos
- Python 3.8+
- pip

### Passos

1. **Clone o repositório**
```bash
git clone https://github.com/jairgramacho/radar-imoveis-pro.git
cd radar-imoveis-pro
```

2. **Crie um ambiente virtual**
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou
.venv\Scripts\activate  # Windows
```

3. **Instale as dependências**
```bash
pip install -r requirements.txt
```

4. **Execute a aplicação**
```bash
python app.py
```

5. **Acesse no navegador**
```
http://localhost:5000
```

## 📁 Estrutura do Projeto

```
radar-imoveis-pro/
├── app.py                 # Aplicação Flask principal
├── requirements.txt       # Dependências do projeto
├── banco_imoveis.txt     # Banco de dados (arquivo de texto)
├── static/
│   ├── css/
│   │   └── style.css     # Estilos CSS customizados
│   └── uploads/          # Fotos dos imóveis
└── templates/
    └── index.html        # Template HTML principal
```

## 🎨 Customização

### Cores Principais
Editar em `static/css/style.css`:
- `--laranja: #f39233` - Cor primária
- `--verde-whatsapp: #25d366` - Cor do botão WhatsApp

### Limite de Upload
Editar em `app.py`:
```python
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
```

### Extensões de Arquivo Permitidas
Editar em `app.py`:
```python
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
```

## 🚀 Próximas Melhorias

- [ ] Foto de perfil do usuário
- [ ] Favoritos e alertas de imóveis
- [ ] Busca com geolocalização no mapa
- [ ] Moderação administrativa avançada
- [ ] Notificações por email e in-app
- [ ] Promoção de anúncios (destacado/premium)
- [ ] Aplicativo mobile (iOS/Android)

## 📧 Contato

Para dúvidas e sugestões, abra uma issue no GitHub.

## 📄 Licença

Este projeto é licenciado sob a MIT License - veja o arquivo LICENSE para detalhes.

---

**Feito com ❤️ por Jair Gramacho**
