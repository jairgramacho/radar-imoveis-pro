#!/usr/bin/env python
"""Script para inicializar o banco de dados"""

from app import app, db

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✓ Banco de dados criado com sucesso!")
