#!/usr/bin/env python3
"""
Script de prueba para el nuevo endpoint /match-practice
"""

import requests
import json
import time

# Configuración
BASE_URL = "http://localhost:8000"  # Ajusta según tu configuración
TEST_USER_ID = "test_user_123"  # Ajusta con un user_id válido
TEST_PRACTICE_ID = "test_practice_456"  # Ajusta con un practice_id válido

def test_match_single_practice():
    """
    Prueba el endpoint /match-practice
    """
    print("🧪 Probando endpoint /match-practice")
    print(f"   - URL: {BASE_URL}/match-practice")
    print(f"   - User ID: {TEST_USER_ID}")
    print(f"   - Practice ID: {TEST_PRACTICE_ID}")
    
    # Preparar datos de la request
    request_data = {
        "user_id": TEST_USER_ID,
        "practice_id": TEST_PRACTICE_ID
    }
    
    try:
        # Hacer la request
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/match-practice",
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        end_time = time.time()
        
        print(f"\n📡 Response Status: {response.status_code}")
        print(f"⏱️  Tiempo de respuesta: {end_time - start_time:.4f} segundos")
        
        if response.status_code == 200:
            # Parsear respuesta
            response_data = response.json()
            
            print(f"\n✅ ÉXITO - Práctica encontrada y match calculado")
            print(f"   - Practice ID: {response_data.get('metadata', {}).get('practice_id')}")
            print(f"   - User ID: {response_data.get('metadata', {}).get('user_id')}")
            
            # Mostrar información de la práctica
            practica = response_data.get('practica', {})
            print(f"\n📋 INFORMACIÓN DE LA PRÁCTICA:")
            print(f"   - Título: {practica.get('title', 'N/A')}")
            print(f"   - Empresa: {practica.get('company', 'N/A')}")
            print(f"   - Ubicación: {practica.get('location', 'N/A')}")
            
            # Mostrar scores de match
            match_scores = practica.get('match_scores', {})
            print(f"\n🎯 SCORES DE MATCH:")
            print(f"   - Hard Skills: {match_scores.get('hard_skills', 0):.2f}%")
            print(f"   - Soft Skills: {match_scores.get('soft_skills', 0):.2f}%")
            print(f"   - Sector Affinity: {match_scores.get('sector_affinity', 0):.2f}%")
            print(f"   - General: {match_scores.get('general', 0):.2f}%")
            print(f"   - 🎆 TOTAL: {match_scores.get('total', 0):.2f}%")
            
            # Mostrar estadísticas de tiempo
            metadata = response_data.get('metadata', {})
            print(f"\n⏱️  ESTADÍSTICAS DE TIEMPO:")
            print(f"   - Tiempo total: {metadata.get('total_time', 0):.4f}s")
            print(f"   - Tiempo de matching: {metadata.get('search_matching_time', 0):.4f}s")
            
        else:
            print(f"\n❌ ERROR - Status {response.status_code}")
            try:
                error_data = response.json()
                print(f"   - Error: {error_data.get('detail', 'Error desconocido')}")
            except:
                print(f"   - Error: {response.text}")
                
    except requests.exceptions.ConnectionError:
        print(f"\n❌ ERROR DE CONEXIÓN")
        print(f"   - No se pudo conectar a {BASE_URL}")
        print(f"   - Verifica que el servidor esté ejecutándose")
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}")

def test_invalid_request():
    """
    Prueba el endpoint con datos inválidos
    """
    print("\n🧪 Probando endpoint con datos inválidos")
    
    # Test 1: Sin user_id
    print("\n📝 Test 1: Sin user_id")
    request_data = {"practice_id": TEST_PRACTICE_ID}
    
    try:
        response = requests.post(
            f"{BASE_URL}/match-practice",
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"   - Status: {response.status_code}")
        if response.status_code == 400:
            print(f"   - ✅ Correcto: user_id es requerido")
        else:
            print(f"   - ❌ Inesperado: {response.text}")
            
    except Exception as e:
        print(f"   - ❌ Error: {e}")
    
    # Test 2: Sin practice_id
    print("\n📝 Test 2: Sin practice_id")
    request_data = {"user_id": TEST_USER_ID}
    
    try:
        response = requests.post(
            f"{BASE_URL}/match-practice",
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"   - Status: {response.status_code}")
        if response.status_code == 400:
            print(f"   - ✅ Correcto: practice_id es requerido")
        else:
            print(f"   - ❌ Inesperado: {response.text}")
            
    except Exception as e:
        print(f"   - ❌ Error: {e}")

if __name__ == "__main__":
    print("🚀 Iniciando pruebas del endpoint /match-practice")
    print("=" * 60)
    
    # Prueba principal
    test_match_single_practice()
    
    # Pruebas de validación
    test_invalid_request()
    
    print("\n" + "=" * 60)
    print("🏁 Pruebas completadas")

