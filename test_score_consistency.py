#!/usr/bin/env python3
"""
Script para verificar que los scores sean consistentes entre match-practices y match-practice
"""

import requests
import json
import time

# Configuración
BASE_URL = "http://localhost:8000"  # Ajusta según tu configuración
TEST_USER_ID = "test_user_123"  # Ajusta con un user_id válido

def test_score_consistency():
    """
    Prueba que los scores sean consistentes entre ambos endpoints
    """
    print("🧪 Probando consistencia de scores entre endpoints")
    print("=" * 60)
    
    try:
        # 1. Obtener prácticas con match-practices
        print("📋 Paso 1: Obteniendo prácticas con /match-practices")
        request_data = {
            "user_id": TEST_USER_ID,
            "limit": 5  # Solo 5 prácticas para comparar
        }
        
        response = requests.post(
            f"{BASE_URL}/match-practices",
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 200:
            print(f"❌ Error en match-practices: {response.status_code}")
            return
        
        match_practices_data = response.json()
        practicas = match_practices_data.get('practicas', [])
        
        if not practicas:
            print("❌ No se encontraron prácticas en match-practices")
            return
        
        print(f"✅ Encontradas {len(practicas)} prácticas")
        
        # 2. Para cada práctica, obtener el score individual con match-practice
        print("\n🔍 Paso 2: Comparando scores individuales")
        print("-" * 60)
        
        for i, practica in enumerate(practicas[:3]):  # Solo las primeras 3
            practice_id = practica.get('id')
            if not practice_id:
                print(f"⚠️  Práctica {i+1} no tiene ID, saltando...")
                continue
            
            print(f"\n📊 Práctica {i+1}: {practica.get('title', 'Sin título')}")
            print(f"   ID: {practice_id}")
            
            # Score de match-practices
            score_match_practices = practica.get('similitud_total', 0)
            print(f"   Score match-practices: {score_match_practices}%")
            
            # Obtener score individual con match-practice
            individual_request = {
                "user_id": TEST_USER_ID,
                "practice_id": practice_id
            }
            
            individual_response = requests.post(
                f"{BASE_URL}/match-practice",
                json=individual_request,
                headers={"Content-Type": "application/json"}
            )
            
            if individual_response.status_code == 200:
                individual_data = individual_response.json()
                individual_practica = individual_data.get('practica', {})
                individual_score = individual_practica.get('match_scores', {}).get('total', 0)
                
                print(f"   Score match-practice: {individual_score}%")
                
                # Comparar scores
                diferencia = abs(score_match_practices - individual_score)
                if diferencia < 1.0:  # Tolerancia de 1%
                    print(f"   ✅ Scores consistentes (diferencia: {diferencia:.2f}%)")
                else:
                    print(f"   ❌ Scores inconsistentes (diferencia: {diferencia:.2f}%)")
                    
                    # Mostrar breakdown de scores
                    print(f"   📊 Breakdown match-practices:")
                    print(f"      - Hard Skills: {practica.get('similitud_requisitos', 0)}%")
                    print(f"      - Sector: {practica.get('afinidad_sector', 0)}%")
                    print(f"      - General: {practica.get('similitud_general', 0)}%")
                    
                    print(f"   📊 Breakdown match-practice:")
                    match_scores = individual_practica.get('match_scores', {})
                    print(f"      - Hard Skills: {match_scores.get('hard_skills', 0)}%")
                    print(f"      - Sector: {match_scores.get('sector_affinity', 0)}%")
                    print(f"      - General: {match_scores.get('general', 0)}%")
            else:
                print(f"   ❌ Error obteniendo score individual: {individual_response.status_code}")
                try:
                    error_data = individual_response.json()
                    print(f"      Error: {error_data.get('detail', 'Error desconocido')}")
                except:
                    print(f"      Error: {individual_response.text}")
            
            # Pausa entre requests
            time.sleep(0.5)
        
        print("\n" + "=" * 60)
        print("🏁 Prueba de consistencia completada")
        
    except requests.exceptions.ConnectionError:
        print(f"\n❌ ERROR DE CONEXIÓN")
        print(f"   - No se pudo conectar a {BASE_URL}")
        print(f"   - Verifica que el servidor esté ejecutándose")
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}")

def test_single_practice_scores():
    """
    Prueba los scores de una práctica específica
    """
    print("\n🧪 Probando scores de práctica específica")
    print("=" * 60)
    
    # Usar una práctica específica si la conoces
    TEST_PRACTICE_ID = "test_practice_456"  # Ajusta con un practice_id válido
    
    try:
        request_data = {
            "user_id": TEST_USER_ID,
            "practice_id": TEST_PRACTICE_ID
        }
        
        response = requests.post(
            f"{BASE_URL}/match-practice",
            json=request_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            practica = data.get('practica', {})
            match_scores = practica.get('match_scores', {})
            
            print(f"✅ Práctica: {practica.get('title', 'Sin título')}")
            print(f"📊 Scores:")
            print(f"   - Hard Skills: {match_scores.get('hard_skills', 0):.2f}%")
            print(f"   - Soft Skills: {match_scores.get('soft_skills', 0):.2f}%")
            print(f"   - Sector Affinity: {match_scores.get('sector_affinity', 0):.2f}%")
            print(f"   - General: {match_scores.get('general', 0):.2f}%")
            print(f"   - 🎆 TOTAL: {match_scores.get('total', 0):.2f}%")
            
            # Verificar que el total sea consistente con los pesos
            calculated_total = (
                match_scores.get('hard_skills', 0) * 0.40 +
                match_scores.get('soft_skills', 0) * 0.10 +
                match_scores.get('sector_affinity', 0) * 0.30 +
                match_scores.get('general', 0) * 0.20
            )
            
            diferencia = abs(calculated_total - match_scores.get('total', 0))
            if diferencia < 0.1:
                print(f"✅ Cálculo de total consistente (diferencia: {diferencia:.4f})")
            else:
                print(f"❌ Cálculo de total inconsistente (diferencia: {diferencia:.4f})")
                print(f"   Calculado: {calculated_total:.2f}%")
                print(f"   Reportado: {match_scores.get('total', 0):.2f}%")
        else:
            print(f"❌ Error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   {error_data.get('detail', 'Error desconocido')}")
            except:
                print(f"   {response.text}")
                
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🚀 Iniciando pruebas de consistencia de scores")
    
    # Prueba principal
    test_score_consistency()
    
    # Prueba de práctica específica
    test_single_practice_scores()
    
    print("\n" + "=" * 60)
    print("🏁 Todas las pruebas completadas")
