import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import logging
from datetime import datetime
import hashlib
import time
from typing import Optional, Union
import mimetypes

# Configurar logging
logger = logging.getLogger(__name__)

class R2StorageService:
    """
    Servicio para manejar subidas a Cloudflare R2 usando boto3
    """
    
    def __init__(self):
        # Configuración del cliente S3 para Cloudflare R2
        self.r2_endpoint = None
        self.r2_access_key_id = None
        self.r2_secret_access_key = None
        self.bucket_name = None
        self.public_url = None
        self.s3_client = None
        self._config_loaded = False
        
        logger.info('🔧 R2StorageService inicializado (configuración lazy)')
    
    def _load_config(self):
        """Cargar configuración desde variables de entorno"""
        if self._config_loaded:
            return
            
        self.r2_endpoint = os.getenv('R2_ENDPOINT')
        self.r2_access_key_id = os.getenv('R2_ACCESS_KEY_ID')
        self.r2_secret_access_key = os.getenv('R2_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('R2_BUCKET_NAME', 'myworkin-uploads')
        self.public_url = os.getenv('NEXT_PUBLIC_R2_PUBLIC_URL') or os.getenv('R2_PUBLIC_URL', '')
        
        # Debug: Mostrar valores de configuración
        logger.info('🔧 Debug configuración R2:')
        logger.info(f'   R2_ENDPOINT: {self.r2_endpoint[:30] + "..." if self.r2_endpoint else "None"}')
        logger.info(f'   R2_ACCESS_KEY_ID: {"CONFIGURADO" if self.r2_access_key_id else "None"}')
        logger.info(f'   R2_SECRET_ACCESS_KEY: {"CONFIGURADO" if self.r2_secret_access_key else "None"}')
        logger.info(f'   R2_BUCKET_NAME: {self.bucket_name}')
        logger.info(f'   NEXT_PUBLIC_R2_PUBLIC_URL: {self.public_url[:30] + "..." if self.public_url else "None"}')
        
        # Validar configuración
        #self._validate_config()
        
        # Inicializar cliente S3
        self.s3_client = boto3.client(
            's3',
            region_name='auto',  # Cloudflare R2 usa 'auto' como región
            endpoint_url=self.r2_endpoint,
            aws_access_key_id=self.r2_access_key_id,
            aws_secret_access_key=self.r2_secret_access_key
        )
        
        self._config_loaded = True
        logger.info('🔧 Configuración R2 cargada correctamente')
    
    def _validate_config(self):
        """Validar que todas las variables de entorno necesarias estén configuradas"""
        missing_vars = []
        
        if not self.r2_endpoint:
            missing_vars.append('R2_ENDPOINT')
        if not self.r2_access_key_id:
            missing_vars.append('R2_ACCESS_KEY_ID')
        if not self.r2_secret_access_key:
            missing_vars.append('R2_SECRET_ACCESS_KEY')
        if not self.public_url:
            missing_vars.append('NEXT_PUBLIC_R2_PUBLIC_URL')
        
        if missing_vars:
            error_msg = f"❌ Variables de entorno R2 faltantes: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info('✅ Configuración R2 válida')
    
    def generate_stable_cv_key(self, cv_id: str) -> str:
        """
        Genera una clave estable para archivos CV basada en el cv_id.
        
        Args:
            cv_id: ID del CV
            
        Returns:
            str: Clave estable para el archivo (ej: "cv/abc123.pdf")
        """
        return f"cv/{cv_id}.pdf"
    
    def generate_stable_cv_url(self, cv_id: str) -> str:
        """
        Genera la URL pública estable para un CV basado en el cv_id.
        
        Args:
            cv_id: ID del CV
            
        Returns:
            str: URL pública estable del CV
        """
        # Cargar configuración si no está cargada
        self._load_config()
        
        stable_key = self.generate_stable_cv_key(cv_id)
        return f"{self.public_url}/{stable_key}"
    
    def generate_pretty_cv_filename(self, cv_data: dict) -> str:
        """
        Genera un nombre bonito para el archivo CV basado en los datos del CV.
        
        Args:
            cv_data: Datos del CV con información personal
            
        Returns:
            str: Nombre bonito para el archivo (ej: "CV_Juan_Perez.pdf")
        """
        try:
            # Intentar extraer el nombre completo
            personal_info = cv_data.get('personalInfo', {}) if cv_data else {}
            full_name = personal_info.get('fullName', '')
            
            if full_name and full_name.strip():
                # Limpiar el nombre (remover caracteres especiales)
                clean_name = ''.join(c for c in full_name if c.isalnum() or c in ' _-').strip()
                clean_name = clean_name.replace(' ', '_')
                return f"CV_{clean_name}.pdf"
            else:
                # Fallback si no hay nombre
                return "CV.pdf"
                
        except Exception:
            # Si hay cualquier error, usar nombre genérico
            return "CV.pdf"

    async def upload_file_to_r2(
        self,
        file_data: Union[bytes, bytearray],
        file_name: str,
        content_type: Optional[str] = None,
        prefix: Optional[str] = None,
        stable_key: Optional[str] = None
    ) -> str:
        """
        Subir un archivo a Cloudflare R2
        
        Args:
            file_data: Datos del archivo en bytes
            file_name: Nombre del archivo
            content_type: Tipo de contenido (opcional, se infiere si no se proporciona)
            prefix: Prefijo opcional para el nombre del archivo (ej: 'cv', 'interview-audio')
            stable_key: Clave fija para el archivo (opcional, sobrescribe prefix/unique generation)
            
        Returns:
            str: URL pública del archivo subido
        """
        # Cargar configuración si no está cargada
        self._load_config()
        
        try:
            #logger.info('📤 === INICIO UPLOAD R2 ===')
            #logger.info(f'📁 Archivo a subir: {file_name}, tamaño: {len(file_data)} bytes')
            
            # Usar clave estable si se proporciona, sino generar única
            if stable_key:
                object_key = stable_key
                #logger.info(f'🔗 Usando clave estable: {object_key}')
            else:
                object_key = self._generate_unique_file_name(file_name, prefix)
                #logger.info(f'🎲 Clave única generada: {object_key}')
            
            # Determinar content type si no se proporciona
            if not content_type:
                content_type = self._get_content_type(file_name)
            
            #logger.info(f'📋 Datos preparados: {object_key}, content-type: {content_type}')
            
            # Configurar headers adicionales para URLs estables (evitar caché de versiones antiguas)
            extra_args = {
                'ContentType': content_type,
                'ACL': 'public-read'
            }
            
            # Si es clave estable, agregar control de caché y nombre de descarga bonito
            if stable_key:
                extra_args['CacheControl'] = 'no-cache, no-store, must-revalidate'
                # Usar el nombre original del archivo para la descarga (más bonito que el ID)
                extra_args['ContentDisposition'] = f'inline; filename="{file_name}"'
            
            # Subir archivo a R2
            response = self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=file_data,
                **extra_args
            )
            
            #logger.info(f'✅ Upload exitoso a R2: ETag={response.get("ETag")}')
            
            # Debug: Verificar valores antes de generar URL
            #logger.info(f'🔍 Debug URL generation:')
            #logger.info(f'   self.public_url: "{self.public_url}"')
            #logger.info(f'   object_key: "{object_key}"')
            
            # Generar URL pública
            public_url = f"{self.public_url}/{object_key}"
            
            #logger.info(f'🔗 URL pública generada: "{public_url}"')
            #logger.info('📤 === FIN UPLOAD R2 ===')
            
            return public_url
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f'❌ Error de AWS/R2: {error_code} - {error_message}')
            raise Exception(f'Error al subir archivo a R2: {error_message}')
        except NoCredentialsError:
            logger.error('❌ Credenciales R2 no configuradas')
            raise Exception('Credenciales R2 no configuradas')
        except Exception as e:
            logger.error(f'❌ Error inesperado en upload: {str(e)}')
            raise Exception(f'Error al subir archivo: {str(e)}')
    
    def _generate_unique_file_name(self, original_name: str, prefix: Optional[str] = None) -> str:
        """
        Generar un nombre de archivo único con timestamp
        
        Args:
            original_name: Nombre original del archivo
            prefix: Prefijo opcional
            
        Returns:
            str: Nombre de archivo único
        """
        timestamp = int(time.time() * 1000)  # Timestamp en milisegundos
        random_suffix = hashlib.md5(f"{timestamp}{original_name}".encode()).hexdigest()[:6]
        
        # Obtener extensión
        extension = original_name.split('.')[-1] if '.' in original_name else ''
        
        # Limpiar nombre base
        base_name = original_name.rsplit('.', 1)[0] if '.' in original_name else original_name
        safe_name = ''.join(c for c in base_name if c.isalnum() or c in '_-').rstrip('_')
        
        prefix_part = f"{prefix}_" if prefix else ""
        extension_part = f".{extension}" if extension else ""
        
        return f"{prefix_part}{safe_name}_{timestamp}_{random_suffix}{extension_part}"
    
    def _get_content_type(self, file_name: str) -> str:
        """
        Obtener el content type basado en la extensión del archivo
        
        Args:
            file_name: Nombre del archivo
            
        Returns:
            str: Content type
        """
        content_type, _ = mimetypes.guess_type(file_name)
        return content_type or 'application/octet-stream'
    
    def validate_file_type(self, file_name: str, allowed_types: list) -> bool:
        """
        Validar tipo de archivo permitido
        
        Args:
            file_name: Nombre del archivo
            allowed_types: Lista de tipos MIME permitidos
            
        Returns:
            bool: True si el archivo es válido
        """
        # Esta función no necesita configuración de R2, solo validación local
        content_type = self._get_content_type(file_name)
        extension = file_name.split('.')[-1].lower() if '.' in file_name else ''
        
        logger.info(f'🔍 Validando tipo de archivo: {file_name}, content-type: {content_type}')
        
        # Validación principal por MIME type
        if content_type in allowed_types:
            logger.info(f'✅ Tipo MIME válido: {content_type}')
            return True
        
        # Validación por extensión para casos especiales
        if content_type == 'application/octet-stream' or not content_type:
            logger.info(f'⚠️ MIME type genérico, validando por extensión: {extension}')
            
            # Validar extensiones de audio
            if any(t.startswith('audio/') for t in allowed_types):
                audio_extensions = ['mp3', 'wav', 'ogg', 'webm', 'm4a', 'aac', 'flac']
                if extension in audio_extensions:
                    logger.info(f'✅ Extensión de audio válida: {extension}')
                    return True
            
            # Validar extensiones de video
            if any(t.startswith('video/') for t in allowed_types):
                video_extensions = ['mp4', 'webm', 'ogg', 'avi', 'mov', 'mkv', 'wmv']
                if extension in video_extensions:
                    logger.info(f'✅ Extensión de video válida: {extension}')
                    return True
        
        logger.info('❌ Tipo de archivo no válido')
        return False
    
    def validate_file_size(self, file_size_bytes: int, max_size_mb: int) -> bool:
        """
        Validar tamaño de archivo
        
        Args:
            file_size_bytes: Tamaño del archivo en bytes
            max_size_mb: Tamaño máximo en MB
            
        Returns:
            bool: True si el archivo es válido
        """
        max_size_bytes = max_size_mb * 1024 * 1024
        return file_size_bytes <= max_size_bytes
    
    async def delete_file_from_r2(self, file_name: str) -> bool:
        """
        Eliminar un archivo de R2 Cloudflare
        
        Args:
            file_name: Nombre del archivo en el bucket (incluyendo prefijo si existe)
            
        Returns:
            bool: True si se eliminó exitosamente, False si no existía
        """
        # Cargar configuración si no está cargada
        self._load_config()
        
        # Validar entrada
        if not file_name or not isinstance(file_name, str) or file_name.strip() == "":
            logger.warning(f'⚠️ Nombre de archivo inválido para eliminar: {file_name}')
            return False
        
        try:
            logger.info(f'🗑️ Eliminando archivo de R2: {file_name}')
            
            # Intentar eliminar el archivo
            response = self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_name
            )
            
            logger.info(f'✅ Archivo eliminado de R2: {file_name}')
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.info(f'ℹ️ Archivo no existía en R2: {file_name}')
                return False  # No es un error, simplemente no existía
            else:
                logger.error(f'❌ Error al eliminar archivo de R2: {error_code} - {e.response["Error"]["Message"]}')
                # No lanzar excepción, solo loggear el error
                return False
        except Exception as e:
            logger.error(f'❌ Error inesperado al eliminar archivo: {str(e)}')
            # No lanzar excepción, solo loggear el error
            return False
    
    def extract_file_name_from_url(self, file_url: str) -> str:
        """
        Extraer el nombre del archivo desde una URL de R2
        
        Args:
            file_url: URL completa del archivo en R2
            
        Returns:
            str: Nombre del archivo en el bucket
        """
        # Cargar configuración si no está cargada
        self._load_config()
        
        try:
            # Validar entrada
            if not file_url or not isinstance(file_url, str) or file_url.strip() == "":
                logger.warning(f'⚠️ URL de archivo inválida: {file_url}')
                return ""
            
            if not self.public_url:
                logger.warning(f'⚠️ URL pública no configurada')
                return ""
            
            # La URL tiene el formato: https://public-url.com/file_name
            # Necesitamos extraer solo el file_name
            if file_url.startswith(self.public_url):
                file_name = file_url[len(self.public_url):].lstrip('/')
                if file_name:  # Verificar que no esté vacío
                    logger.info(f'📝 Nombre extraído de URL: {file_name}')
                    return file_name
                else:
                    logger.warning(f'⚠️ Nombre de archivo vacío extraído de URL: {file_url}')
                    return ""
            else:
                logger.warning(f'⚠️ URL no coincide con la configuración: {file_url}')
                return ""
                
        except Exception as e:
            logger.error(f'❌ Error al extraer nombre de archivo de URL: {str(e)}')
            return ""

# Instancia global del servicio
r2_storage = R2StorageService()

# Constantes para tipos de archivo permitidos
ALLOWED_FILE_TYPES = {
    'CV': [
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ],
    'AUDIO': [
        'audio/mpeg',
        'audio/wav',
        'audio/ogg',
        'audio/webm',
        'audio/mp3',
        'audio/m4a',
        'audio/aac',
        'audio/flac'
    ],
    'VIDEO': [
        'video/mp4',
        'video/webm',
        'video/ogg',
        'video/avi',
        'video/mov',
        'video/mkv',
        'video/wmv'
    ],
    'IMAGE': [
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp'
    ]
}

# Límites de tamaño por tipo de archivo (en MB)
FILE_SIZE_LIMITS = {
    'CV': 10,     # 10MB para CVs
    'AUDIO': 50,  # 50MB para audios de entrevista
    'VIDEO': 100, # 100MB para videos de entrevista
    'IMAGE': 5,   # 5MB para imágenes
}
