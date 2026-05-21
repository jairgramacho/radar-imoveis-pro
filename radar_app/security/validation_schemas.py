"""Pydantic schemas para validação de entrada (OWASP Input Validation)."""

from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class UsuarioCadastroSchema(BaseModel):
    """Schema para validação de cadastro de novo usuário."""
    nome: str = Field(..., min_length=3, max_length=120)
    email: EmailStr
    senha: str = Field(..., min_length=12, max_length=128)
    whatsapp: str = Field(..., min_length=14, max_length=15)
    consent_terms: bool = Field(default=False)
    
    @field_validator('nome')
    @classmethod
    def validar_nome(cls, v):
        # Remove caracteres especiais perigosos
        if not re.match(r'^[a-zA-Z0-9\s\.\-]{3,120}$', v):
            raise ValueError('Nome contém caracteres inválidos')
        return v.strip()
    
    @field_validator('whatsapp')
    @classmethod
    def validar_whatsapp(cls, v):
        # Valida formato: (XX) XXXXX-XXXX ou (XX) XXXX-XXXX
        if not re.match(r'^\(\d{2}\)\s?\d{4,5}-\d{4}$', v):
            raise ValueError('WhatsApp em formato inválido')
        return v.strip()
    
    @field_validator('senha')
    @classmethod
    def validar_senha_forca(cls, v):
        # Exige: maiúscula, minúscula, número, caractere especial
        if not re.search(r'[A-Z]', v):
            raise ValueError('Senha deve ter letra maiúscula')
        if not re.search(r'[a-z]', v):
            raise ValueError('Senha deve ter letra minúscula')
        if not re.search(r'[0-9]', v):
            raise ValueError('Senha deve ter número')
        if not re.search(r'[!@#$%^&*]', v):
            raise ValueError('Senha deve ter caractere especial (!@#$%^&*)')
        return v


class UsuarioLoginSchema(BaseModel):
    """Schema para validação de login."""
    email: EmailStr
    senha: str = Field(..., min_length=1, max_length=128)


class ImovelDescricaoSchema(BaseModel):
    """Schema para validação de descrição de imóvel."""
    descricao: str = Field(..., max_length=1000)
    
    @field_validator('descricao')
    @classmethod
    def validar_descricao(cls, v):
        if len(v.strip()) < 10:
            raise ValueError('Descrição deve ter no mínimo 10 caracteres')
        return v.strip()


class MensagemChatSchema(BaseModel):
    """Schema para validação de mensagem de chat."""
    mensagem: str = Field(..., min_length=1, max_length=5000)
    titulo: str = Field(default='', max_length=200)
    
    @field_validator('mensagem')
    @classmethod
    def validar_mensagem(cls, v):
        if len(v.strip()) < 1:
            raise ValueError('Mensagem não pode estar vazia')
        return v.strip()
    
    @field_validator('titulo')
    @classmethod
    def validar_titulo(cls, v):
        if v and len(v.strip()) < 3:
            raise ValueError('Título deve ter no mínimo 3 caracteres')
        return v.strip()


class AvaliacaoSchema(BaseModel):
    """Schema para validação de avaliação."""
    estrelas: int = Field(..., ge=1, le=5)
    comentario: str = Field(default='', max_length=500)
    
    @field_validator('comentario')
    @classmethod
    def validar_comentario(cls, v):
        if v and len(v.strip()) < 5:
            raise ValueError('Comentário deve ter no mínimo 5 caracteres')
        return v.strip()


class ConfiguracaoContaSchema(BaseModel):
    """Schema para validação de alterações de conta."""
    nome: str = Field(..., min_length=3, max_length=120)
    whatsapp: str = Field(..., min_length=14, max_length=15)
    nova_senha: str = Field(default='', max_length=128)
    
    @field_validator('nome')
    @classmethod
    def validar_nome(cls, v):
        if not re.match(r'^[a-zA-Z0-9\s\.\-]{3,120}$', v):
            raise ValueError('Nome contém caracteres inválidos')
        return v.strip()
    
    @field_validator('whatsapp')
    @classmethod
    def validar_whatsapp(cls, v):
        if not re.match(r'^\(\d{2}\)\s?\d{4,5}-\d{4}$', v):
            raise ValueError('WhatsApp em formato inválido')
        return v.strip()
