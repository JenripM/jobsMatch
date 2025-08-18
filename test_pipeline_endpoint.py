#!/usr/bin/env python3
"""
Script de prueba para los endpoints del pipeline de procesamiento de ofertas laborales
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_complete_endpoint():
    """Prueba el endpoint completo de pipeline con configuración compleja"""
    print("🧪 Probando endpoint completo de pipeline...")
    
    url = f"{BASE_URL}/process-jobs-pipeline"
    
    # Configuración completa con múltiples migraciones
    config = {
        "migrations": [
            {
                "source_collection": "practicas",
                "target_collection": "practicas_embeddings_test",
                "job_level": "practicante"
            }
        ],
        "cleanups": [
            {
                "collection_name": "practicas",
                "since_days": 5
            },
            {
                "collection_name": "practicas_embeddings_test",
                "since_days": 7
            }
        ],
        "sections": {
            "enable_migration": True,
            "enable_metadata": True,
            "enable_embeddings": True,
            "enable_cache_clear": True,
            "enable_cleanup": True
        },
        "overwrite_metadata": False,
        "overwrite_embeddings": False,
        "days_back": 5  # Solo procesar últimos 5 días para optimización
    }
    
    try:
        response = requests.post(url, json=config)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Endpoint completo funcionó correctamente")
            print(f"   - Duración total: {result.get('total_duration', 0):.2f}s")
            print(f"   - Éxito: {result.get('success', False)}")
            
            # Mostrar detalles de cada paso
            steps = result.get('steps', {})
            for step_name, step_data in steps.items():
                print(f"   - {step_name}: {step_data.get('status', 'unknown')} ({step_data.get('duration', 0):.2f}s)")
                if step_data.get('details'):
                    details = step_data['details']
                    if 'total_migrated' in details:
                        print(f"     * Migrados: {details['total_migrated']}")
                    if 'total_metadata_generated' in details:
                        print(f"     * Metadatos: {details['total_metadata_generated']}")
                    if 'total_embeddings_generated' in details:
                        print(f"     * Embeddings: {details['total_embeddings_generated']}")
            
            # Mostrar resumen
            summary = result.get('summary', {})
            print(f"   - Resumen: {summary}")
            
        else:
            print(f"❌ Error en endpoint completo: {response.status_code}")
            print(f"   - Respuesta: {response.text}")
            
    except Exception as e:
        print(f"❌ Excepción en endpoint completo: {e}")

def test_invalid_config():
    """Prueba el endpoint con configuración inválida"""
    print("🧪 Probando configuración inválida...")
    
    url = f"{BASE_URL}/process-jobs-pipeline"
    
    # Configuración inválida (sin migrations)
    invalid_config = {
        "sections": {
            "enable_migration": True,
            "enable_metadata": True,
            "enable_embeddings": True,
            "enable_cache_clear": True,
            "enable_cleanup": False
        },
        "overwrite_metadata": False,
        "overwrite_embeddings": False,
        "days_back": 5
    }
    
    try:
        response = requests.post(url, json=invalid_config)
        
        if response.status_code == 422:
            print("✅ Validación funcionó correctamente (error 422 esperado)")
            error_detail = response.json()
            print(f"   - Error: {error_detail}")
        else:
            print(f"❌ Error inesperado: {response.status_code}")
            print(f"   - Respuesta: {response.text}")
            
    except Exception as e:
        print(f"❌ Excepción en test de configuración inválida: {e}")

def test_basic_config():
    """Prueba el endpoint con configuración básica (una sola migración)"""
    print("🧪 Probando configuración básica...")
    
    url = f"{BASE_URL}/process-jobs-pipeline"
    
    # Configuración básica con una sola migración
    config = {
        "migrations": [
            {
                "source_collection": "practicas",
                "target_collection": "practicas_embeddings_test",
                "job_level": "practicante"
            }
        ],
        "sections": {
            "enable_migration": True,
            "enable_metadata": True,
            "enable_embeddings": True,
            "enable_cache_clear": True,
            "enable_cleanup": False
        },
        "overwrite_metadata": False,
        "overwrite_embeddings": False,
        "days_back": 5
    }
    
    try:
        response = requests.post(url, json=config)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Configuración básica funcionó correctamente")
            print(f"   - Duración total: {result.get('total_duration', 0):.2f}s")
            print(f"   - Éxito: {result.get('success', False)}")
            
            # Mostrar detalles de cada paso
            steps = result.get('steps', {})
            for step_name, step_data in steps.items():
                print(f"   - {step_name}: {step_data.get('status', 'unknown')} ({step_data.get('duration', 0):.2f}s)")
            
            # Mostrar resumen
            summary = result.get('summary', {})
            print(f"   - Resumen: {summary}")
            
        else:
            print(f"❌ Error en configuración básica: {response.status_code}")
            print(f"   - Respuesta: {response.text}")
            
    except Exception as e:
        print(f"❌ Excepción en configuración básica: {e}")

def test_cleanup_only():
    """Prueba el endpoint solo con limpieza de documentos"""
    print("🧪 Probando solo limpieza de documentos...")
    
    url = f"{BASE_URL}/process-jobs-pipeline"
    
    # Configuración solo para limpieza
    config = {
        "migrations": [
            {
                "source_collection": "practicas",
                "target_collection": "practicas_embeddings_test",
                "job_level": "practicante"
            }
        ],
        "cleanups": [
            {
                "collection_name": "practicas",
                "since_days": 5
            },
            {
                "collection_name": "practicas_embeddings_test",
                "since_days": 7
            }
        ],
        "sections": {
            "enable_migration": False,
            "enable_metadata": False,
            "enable_embeddings": False,
            "enable_cache_clear": False,
            "enable_cleanup": True
        },
        "overwrite_metadata": False,
        "overwrite_embeddings": False,
        "days_back": 5
    }
    
    try:
        response = requests.post(url, json=config)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Limpieza funcionó correctamente")
            print(f"   - Duración total: {result.get('total_duration', 0):.2f}s")
            print(f"   - Éxito: {result.get('success', False)}")
            
            # Mostrar detalles de cada paso
            steps = result.get('steps', {})
            for step_name, step_data in steps.items():
                print(f"   - {step_name}: {step_data.get('status', 'unknown')} ({step_data.get('duration', 0):.2f}s)")
            
            # Mostrar resumen
            summary = result.get('summary', {})
            print(f"   - Resumen: {summary}")
            
        else:
            print(f"❌ Error en limpieza: {response.status_code}")
            print(f"   - Respuesta: {response.text}")
            
    except Exception as e:
        print(f"❌ Excepción en limpieza: {e}")

if __name__ == "__main__":
    print("🚀 Iniciando tests del endpoint de pipeline...")
    print("=" * 50)
    
    # Test 1: Configuración básica
    test_basic_config()
    #print()
    
    # Test 2: Configuración completa
    #test_complete_endpoint()
    #print()
    
    # Test 3: Configuración inválida
    #test_invalid_config()
    #print()
    
    # Test 4: Solo limpieza
    #test_cleanup_only()
    print()
    
    print("🏁 Tests completados")
