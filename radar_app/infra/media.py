import importlib
import io
import os
from datetime import datetime

from flask import current_app, url_for
from PIL import Image
from werkzeug.utils import secure_filename


def cloudinary_configurado():
    """Retorna True quando as credenciais do Cloudinary estão configuradas."""
    return all([
        os.getenv('CLOUDINARY_CLOUD_NAME', '').strip(),
        os.getenv('CLOUDINARY_API_KEY', '').strip(),
        os.getenv('CLOUDINARY_API_SECRET', '').strip(),
    ])


def cloudinary_uploader():
    """Carrega uploader do Cloudinary sob demanda para evitar hard dependency em dev."""
    if not cloudinary_configurado():
        return None

    try:
        cloudinary_module = importlib.import_module('cloudinary')
        uploader_module = importlib.import_module('cloudinary.uploader')
        cloudinary_module.config(
            cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME', ''),
            api_key=os.getenv('CLOUDINARY_API_KEY', ''),
            api_secret=os.getenv('CLOUDINARY_API_SECRET', ''),
            secure=True,
        )
        return uploader_module
    except Exception as error:
        current_app.logger.warning('Cloudinary indisponível no ambiente: %s', str(error))
        return None


def foto_eh_url(valor):
    """Identifica se o valor já é uma URL externa."""
    texto = (valor or '').strip().lower()
    return texto.startswith('http://') or texto.startswith('https://')


def foto_url(valor, external=False):
    """Resolve URL de foto para arquivos locais e URLs externas."""
    if not valor:
        return url_for('static', filename='css/style.css', _external=external)
    if foto_eh_url(valor):
        return valor
    return url_for('static', filename='uploads/' + valor, _external=external)


def url_cloudinary_og(url):
    """Retorna URL Cloudinary otimizada para cards sociais em formato retrato."""
    if not url:
        return url

    texto = (url or '').strip()
    if 'res.cloudinary.com' not in texto or '/image/upload/' not in texto:
        return texto

    if '/image/upload/c_fill,w_1080,h_1350,q_auto,f_auto/' in texto:
        return texto

    return texto.replace(
        '/image/upload/',
        '/image/upload/c_fill,w_1080,h_1350,q_auto,f_auto/',
        1,
    )


def arquivo_upload_existe(valor):
    """Valida se arquivo local de upload existe no disco."""
    if not valor or foto_eh_url(valor):
        return True
    caminho = os.path.join(current_app.config['UPLOAD_FOLDER'], valor)
    return os.path.exists(caminho)


def resolver_foto_preview(imovel, public_url_builder):
    """Escolhe a melhor foto válida para preview social."""
    candidatas = []
    if imovel.foto:
        candidatas.append(imovel.foto)
    if imovel.fotos:
        candidatas.extend([foto.arquivo for foto in imovel.fotos if foto.arquivo])

    for foto_base in candidatas:
        if not arquivo_upload_existe(foto_base):
            continue
        if foto_eh_url(foto_base):
            return url_cloudinary_og(foto_base)
        return public_url_builder('static', filename='uploads/' + foto_base)

    return public_url_builder('og_placeholder', tipo=imovel.tipo, cidade=imovel.cidade)


def allowed_file(filename, allowed_extensions):
    """Verifica se o arquivo é permitido."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def processar_imagem(arquivo, allowed_extensions):
    """Processa imagem, convertendo HEIC/HEIF para JPG quando necessário."""
    try:
        if not arquivo or not arquivo.filename:
            return None, False

        ext = arquivo.filename.rsplit('.', 1)[1].lower() if '.' in arquivo.filename else ''
        if ext not in allowed_extensions:
            return None, False

        nome_original = secure_filename(arquivo.filename)
        timestamp = int(datetime.utcnow().timestamp())

        if ext in ['heic', 'heif']:
            try:
                imagem = Image.open(arquivo.stream)

                if imagem.mode in ('RGBA', 'LA', 'P'):
                    imagem = imagem.convert('RGB')

                nome_sem_ext = nome_original.rsplit('.', 1)[0]
                nome_novo = f"{timestamp}_{nome_sem_ext}.jpg"

                uploader = cloudinary_uploader()
                if uploader:
                    buffer = io.BytesIO()
                    imagem.save(buffer, 'JPEG', quality=85, optimize=True)
                    buffer.seek(0)
                    upload_result = uploader.upload(
                        buffer,
                        folder='radar-imoveis-pro',
                        public_id=nome_novo.rsplit('.', 1)[0],
                        resource_type='image',
                        overwrite=False,
                    )
                    return upload_result.get('secure_url'), True

                caminho = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_novo)
                imagem.save(caminho, 'JPEG', quality=85, optimize=True)
                return nome_novo, True
            except Exception as error:
                current_app.logger.warning('Erro ao converter HEIC: %s', str(error))
                return None, False

        nome_novo = f"{timestamp}_{nome_original}"
        uploader = cloudinary_uploader()
        if uploader:
            arquivo.stream.seek(0)
            upload_result = uploader.upload(
                arquivo.stream,
                folder='radar-imoveis-pro',
                public_id=nome_novo.rsplit('.', 1)[0],
                resource_type='image',
                overwrite=False,
            )
            return upload_result.get('secure_url'), True

        caminho = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_novo)
        arquivo.save(caminho)
        return nome_novo, True

    except Exception as error:
        current_app.logger.warning('Erro ao processar imagem: %s', str(error), exc_info=True)
        return None, False
