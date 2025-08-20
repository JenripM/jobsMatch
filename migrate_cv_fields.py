#!/usr/bin/env python3
"""
Script de migración para CVs con campos faltantes

Este script identifica todos los CVs en la colección "userCVs" que tienen el campo "data"
pero les faltan los campos embeddings o fileUrl, y los genera usando las
funciones existentes del sistema.

Requisitos:
- CV debe tener campo "data" (si no lo tiene, se ignora)
- Solo procesa CVs que les falten embeddings o fileUrl
- No toca CVs que ya tienen todos los campos
- Metadata se genera internamente para embeddings pero no se guarda

Uso:
    python migrate_cv_fields.py
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import traceback
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Importar configuración y servicios
from db import db_users
from services.user_service import (
    generate_cv_embeddings,
    extract_user_metadata,
    infer_cv_structured_data
)
from services.pdf_generator_service import CVPDFGenerator
from services.storage_service import r2_storage

class CVMigrationPipeline:
    def __init__(self):
        self.stats = {
            'total_cvs_found': 0,
            'cvs_with_data': 0,
            'cvs_needing_migration': 0,
            'cvs_migrated_successfully': 0,
            'cvs_failed_migration': 0,
            'errors': []
        }
    
    async def find_cvs_needing_migration(self) -> List[Dict[str, Any]]:

        """
        Busca todos los CVs que necesitan migración (tienen 'data' pero les faltan embeddings o fileUrl)
        """
        print("🔍 Buscando CVs que necesitan migración...")
        
        try:
            # Obtener todos los CVs de la colección userCVs
            cvs_ref = db_users.collection("userCVs")
            cvs_snapshot = cvs_ref.stream()
            
            cvs_needing_migration = []
            
            for cv_doc in cvs_snapshot:
                self.stats['total_cvs_found'] += 1
                cv_data = cv_doc.to_dict()
                cv_id = cv_doc.id
                
                # Verificar si tiene el campo 'data'
                if not cv_data.get('data'):
                    print(f"   ⏭️ CV {cv_id}: No tiene campo 'data', ignorando")
                    continue
                
                self.stats['cvs_with_data'] += 1
                
                # Verificar qué campos faltan (solo embeddings y fileUrl se guardan)
                missing_fields = []
                if not cv_data.get('embeddings'):
                    missing_fields.append('embeddings')
                if not cv_data.get('fileUrl'):
                    missing_fields.append('fileUrl')
                
                if missing_fields:
                    print(f"   🔧 CV {cv_id}: Faltan campos {missing_fields}")
                    cvs_needing_migration.append({
                        'id': cv_id,
                        'data': cv_data,
                        'missing_fields': missing_fields
                    })
                    self.stats['cvs_needing_migration'] += 1
                # No imprimir los CVs que ya están completos para evitar spam
            
            print(f"📊 Estadísticas de búsqueda:")
            print(f"   - Total CVs encontrados: {self.stats['total_cvs_found']}")
            print(f"   - CVs con campo 'data': {self.stats['cvs_with_data']}")
            print(f"   - CVs que necesitan migración: {self.stats['cvs_needing_migration']}")
            
            return cvs_needing_migration
            
        except Exception as e:
            print(f"❌ Error buscando CVs: {e}")
            self.stats['errors'].append(f"Error en búsqueda: {str(e)}")
            return []
    
    async def generate_missing_metadata(self, cv_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Genera metadata para un CV usando su campo 'data' (solo para embeddings)
        """
        try:
            print(f"   🤖 Generando metadata...")
            # Convertir cv_data a string para generar metadata
            cv_text = json.dumps(cv_data, ensure_ascii=False)
            metadata = await extract_user_metadata(cv_text)
            
            if metadata:
                print(f"   ✅ Metadata generada exitosamente")
                return metadata
            else:
                print(f"   ❌ No se pudo generar metadata")
                return None
                
        except Exception as e:
            print(f"   ❌ Error generando metadata: {e}")
            return None
    
    async def generate_missing_embeddings(self, cv_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Genera embeddings para un CV usando su campo 'data'
        """
        try:
            print(f"   🔗 Generando embeddings...")
            # Convertir cv_data a string para generar embeddings
            cv_text = json.dumps(cv_data, ensure_ascii=False)
            embeddings = await generate_cv_embeddings(cv_text)
            
            if embeddings:
                print(f"   ✅ Embeddings generados exitosamente")
                return embeddings
            else:
                print(f"   ❌ No se pudieron generar embeddings")
                return None
                
        except Exception as e:
            print(f"   ❌ Error generando embeddings: {e}")
            return None
    
    async def generate_missing_file_url(self, cv_data: Dict[str, Any]) -> Optional[str]:
        """
        Genera fileUrl para un CV generando un PDF y subiéndolo a R2
        """
        try:
            print(f"   📄 Generando PDF y subiendo a R2...")
            
            # Generar PDF a partir del cv_data
            pdf_content, pdf_file_name = CVPDFGenerator.generate_pdf_from_cv_data(cv_data)
            
            # Subir a R2
            file_url = await r2_storage.upload_file_to_r2(
                file_data=pdf_content,
                file_name=pdf_file_name,
                content_type="application/pdf",
                prefix="cv"
            )
            
            print(f"   ✅ PDF generado y subido exitosamente: {file_url}")
            return file_url
            
        except Exception as e:
            print(f"   ❌ Error generando fileUrl: {e}")
            return None
    
    async def migrate_cv(self, cv_info: Dict[str, Any]) -> bool:
        """
        Migra un CV específico generando los campos faltantes
        """
        cv_id = cv_info['id']
        cv_data = cv_info['data']
        missing_fields = cv_info['missing_fields']
        
        print(f"\n🔄 Migrando CV {cv_id}...")
        print(f"   📋 Campos faltantes: {missing_fields}")
        
        start_time = time.time()
        update_payload = {}
        
        try:
            # Generar embeddings si faltan (metadata se genera internamente)
            if 'embeddings' in missing_fields:
                embeddings = await self.generate_missing_embeddings(cv_data['data'])
                if embeddings:
                    update_payload['embeddings'] = embeddings
                else:
                    print(f"   ❌ No se pudieron generar embeddings - DETENIENDO MIGRACIÓN")
                    raise Exception("Error crítico: No se pudieron generar embeddings")
            
            # Generar fileUrl si falta
            if 'fileUrl' in missing_fields:
                file_url = await self.generate_missing_file_url(cv_data['data'])
                if file_url:
                    update_payload['fileUrl'] = file_url
                else:
                    print(f"   ❌ No se pudo generar fileUrl - DETENIENDO MIGRACIÓN")
                    raise Exception("Error crítico: No se pudo generar fileUrl")
            
            # Actualizar en Firestore si hay campos para actualizar
            if update_payload:
                # Agregar timestamp de actualización
                update_payload['updatedAt'] = datetime.now()
                
                # Actualizar documento
                doc_ref = db_users.collection("userCVs").document(cv_id)
                doc_ref.update(update_payload)
                
                migration_time = time.time() - start_time
                print(f"   ✅ CV migrado exitosamente en {migration_time:.2f}s")
                print(f"   📝 Campos actualizados: {list(update_payload.keys())}")
                
                return True
            else:
                print(f"   ❌ No se pudo generar ningún campo faltante - DETENIENDO MIGRACIÓN")
                raise Exception("Error crítico: No se pudo generar ningún campo faltante")
                
        except Exception as e:
            migration_time = time.time() - start_time
            error_msg = f"Error migrando CV {cv_id} después de {migration_time:.2f}s: {str(e)}"
            print(f"   ❌ {error_msg}")
            self.stats['errors'].append(error_msg)
            # Re-lanzar la excepción para detener el proceso
            raise
    
    async def run_migration(self):
        """
        Ejecuta el pipeline completo de migración
        """
        print("🚀 Iniciando pipeline de migración de CVs...")
        print("=" * 60)
        
        start_time = time.time()
        
        try:
            # 1. Buscar CVs que necesitan migración
            cvs_to_migrate = await self.find_cvs_needing_migration()
            
            if not cvs_to_migrate:
                print("✅ No hay CVs que necesiten migración")
                return
            
            print(f"\n🔄 Iniciando migración de {len(cvs_to_migrate)} CVs...")
            print("=" * 60)
            
            # 2. Migrar cada CV
            for i, cv_info in enumerate(cvs_to_migrate, 1):
                print(f"\n📋 Procesando CV {i}/{len(cvs_to_migrate)}")
                
                success = await self.migrate_cv(cv_info)
                
                if success:
                    self.stats['cvs_migrated_successfully'] += 1
                else:
                    self.stats['cvs_failed_migration'] += 1
                
                # Pausa entre CVs para no sobrecargar los servicios
                if i < len(cvs_to_migrate):
                    print("   ⏳ Pausa de 2 segundos...")
                    await asyncio.sleep(2)
            
            # 3. Mostrar estadísticas finales
            total_time = time.time() - start_time
            self.print_final_stats(total_time)
            
        except Exception as e:
            total_time = time.time() - start_time
            print(f"❌ Error en el pipeline de migración después de {total_time:.2f}s: {e}")
            print(f"Stack trace: {traceback.format_exc()}")
            self.stats['errors'].append(f"Error general del pipeline: {str(e)}")
    
    def print_final_stats(self, total_time: float):
        """
        Imprime las estadísticas finales de la migración
        """
        print("\n" + "=" * 60)
        print("📊 ESTADÍSTICAS FINALES DE MIGRACIÓN")
        print("=" * 60)
        print(f"⏱️ Tiempo total: {total_time:.2f} segundos")
        print(f"📋 Total CVs encontrados: {self.stats['total_cvs_found']}")
        print(f"📄 CVs con campo 'data': {self.stats['cvs_with_data']}")
        print(f"🔧 CVs que necesitaban migración: {self.stats['cvs_needing_migration']}")
        print(f"✅ CVs migrados exitosamente: {self.stats['cvs_migrated_successfully']}")
        print(f"❌ CVs con fallos en migración: {self.stats['cvs_failed_migration']}")
        
        if self.stats['errors']:
            print(f"\n⚠️ Errores encontrados ({len(self.stats['errors'])}):")
            for i, error in enumerate(self.stats['errors'], 1):
                print(f"   {i}. {error}")
        
        print("=" * 60)

async def main():
    """
    Función principal del script
    """
    print("🚀 Script de migración de campos de CV")
    print("Este script identificará y migrará CVs con campos faltantes")
    print("=" * 60)
    
    # Verificar configuración R2 antes de empezar
    print("🔍 Verificando configuración R2...")
    
    # Debug: Mostrar variables de entorno cargadas
    print("   📋 Variables de entorno cargadas:")
    print(f"      R2_ENDPOINT: {'✅ Configurado' if os.getenv('R2_ENDPOINT') else '❌ No configurado'}")
    print(f"      R2_ACCESS_KEY_ID: {'✅ Configurado' if os.getenv('R2_ACCESS_KEY_ID') else '❌ No configurado'}")
    print(f"      R2_SECRET_ACCESS_KEY: {'✅ Configurado' if os.getenv('R2_SECRET_ACCESS_KEY') else '❌ No configurado'}")
    print(f"      NEXT_PUBLIC_R2_PUBLIC_URL: {'✅ Configurado' if os.getenv('NEXT_PUBLIC_R2_PUBLIC_URL') else '❌ No configurado'}")
    print(f"      R2_BUCKET_NAME: {'✅ Configurado' if os.getenv('R2_BUCKET_NAME') else '⚠️ Usando default (myworkin-uploads)'}")
    
    try:
        # Intentar cargar configuración R2
        r2_storage._load_config()
        
        # Verificar que realmente se puede conectar haciendo una prueba
        print("   🔗 Probando conexión con R2...")
        test_data = b"test"
        test_url = await r2_storage.upload_file_to_r2(
            file_data=test_data,
            file_name="test_migration.txt",
            content_type="text/plain",
            prefix="test"
        )
        print(f"   ✅ Conexión R2 exitosa - URL de prueba: {test_url}")
        
        # Limpiar archivo de prueba (opcional)
        try:
            await r2_storage.delete_file_from_r2("test/test_migration.txt")
            print("   🧹 Archivo de prueba eliminado")
        except Exception as cleanup_error:
            print(f"   ⚠️ No se pudo eliminar archivo de prueba (no crítico): {cleanup_error}")
            
        print("✅ Configuración R2 verificada correctamente")
        
    except Exception as e:
        print(f"❌ Error en configuración R2: {e}")
        print("🔧 Variables de entorno necesarias:")
        print("   - R2_ENDPOINT")
        print("   - R2_ACCESS_KEY_ID") 
        print("   - R2_SECRET_ACCESS_KEY")
        print("   - NEXT_PUBLIC_R2_PUBLIC_URL")
        print("   - R2_BUCKET_NAME (opcional, default: myworkin-uploads)")
        print(f"🔍 Debug: {str(e)}")
        return
    
    # Confirmación del usuario
    response = input("¿Deseas continuar con la migración? (y/N): ")
    if response.lower() != 'y':
        print("❌ Migración cancelada por el usuario")
        return
    
    # Crear y ejecutar el pipeline
    pipeline = CVMigrationPipeline()
    await pipeline.run_migration()

if __name__ == "__main__":
    asyncio.run(main())
