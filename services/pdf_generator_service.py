"""
Servicio para generar PDFs a partir de cvData usando la plantilla Harvard
"""

import json
from typing import Dict, Any, Tuple
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import black, blue
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from io import BytesIO
import re


class CVPDFGenerator:
    """Generador de PDFs para CVs usando plantilla Harvard"""
    
    @staticmethod
    def _format_technologies(technologies) -> str:
        """
        Formatea tecnologías manejando tanto listas como strings.
        
        Args:
            technologies: Lista de tecnologías o string con tecnologías separadas por comas
            
        Returns:
            str: Tecnologías formateadas como string separado por comas
        """
        if not technologies:
            return ""
        
        # Si es string, dividir por comas y limpiar espacios
        if isinstance(technologies, str):
            tech_list = [tech.strip() for tech in technologies.split(',') if tech.strip()]
            return ', '.join(tech_list)
        
        # Si es lista, unir directamente
        if isinstance(technologies, list):
            return ', '.join(str(tech) for tech in technologies if tech)
        
        # Fallback para otros tipos
        return str(technologies)
    
    @staticmethod
    def generate_pdf_from_cv_data(cv_data: Dict[str, Any]) -> Tuple[bytes, str]:
        """
        Genera un PDF a partir de cvData usando la plantilla Harvard
        
        Args:
            cv_data: Diccionario con los datos del CV
            
        Returns:
            Tuple[bytes, str]: (contenido del PDF como bytes, nombre del archivo)
        """
        try:
            # Crear buffer para el PDF
            buffer = BytesIO()
            
            # Crear documento PDF
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=0.5*inch,
                leftMargin=0.5*inch,
                topMargin=0.5*inch,
                bottomMargin=0.5*inch
            )
            
            # Obtener estilos
            styles = getSampleStyleSheet()
            
            # Crear estilos personalizados
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                alignment=TA_CENTER,
                spaceAfter=12,
                fontName='Times-Bold'
            )
            
            contact_style = ParagraphStyle(
                'ContactInfo',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_CENTER,
                spaceAfter=12,
                fontName='Times-Roman'
            )
            
            section_style = ParagraphStyle(
                'SectionTitle',
                parent=styles['Heading2'],
                fontSize=11,
                alignment=TA_CENTER,
                spaceAfter=8,
                fontName='Times-Bold'
            )
            
            company_style = ParagraphStyle(
                'Company',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_LEFT,
                spaceAfter=4,
                fontName='Times-Bold'
            )
            
            position_style = ParagraphStyle(
                'Position',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_LEFT,
                spaceAfter=4,
                fontName='Times-Bold'
            )
            
            normal_style = ParagraphStyle(
                'Normal',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_JUSTIFY,
                spaceAfter=4,
                fontName='Times-Roman'
            )
            
            bullet_style = ParagraphStyle(
                'Bullet',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_LEFT,
                spaceAfter=2,
                leftIndent=20,
                fontName='Times-Roman'
            )
            
            # Lista de elementos del PDF
            story = []
            
            # 1. NOMBRE (centrado)
            personal_info = cv_data.get('personalInfo', {})
            full_name = personal_info.get('fullName', '')
            if full_name:
                story.append(Paragraph(full_name, title_style))
            
            # 2. INFORMACIÓN DE CONTACTO (centrada)
            contact_items = []
            if personal_info.get('email'):
                contact_items.append(personal_info['email'])
            if personal_info.get('phone'):
                contact_items.append(personal_info['phone'])
            if personal_info.get('address'):
                contact_items.append(personal_info['address'])
            if personal_info.get('linkedIn'):
                contact_items.append(personal_info['linkedIn'])
            if personal_info.get('website'):
                contact_items.append(personal_info['website'])
            
            if contact_items:
                contact_line = ' • '.join(contact_items)
                story.append(Paragraph(contact_line, contact_style))
                story.append(Spacer(1, 12))
            
            # 3. RESUMEN
            summary = personal_info.get('summary', '')
            if summary:
                # Limpiar saltos de línea múltiples
                summary_clean = re.sub(r'\n+', ' ', summary)
                story.append(Paragraph(summary_clean, normal_style))
                story.append(Spacer(1, 12))
            
            # 4. EXPERIENCIA LABORAL Y PROYECTOS
            work_experience = cv_data.get('workExperience', [])
            projects = cv_data.get('projects', [])
            
            if work_experience or projects:
                story.append(Paragraph('Experiencia', section_style))
                
                # Experiencia Laboral
                for exp in work_experience:
                    # Empresa
                    company = exp.get('company', '')
                    if company:
                        story.append(Paragraph(company, company_style))
                    
                    # Descripción de la empresa
                    description = exp.get('description', '')
                    if description:
                        story.append(Paragraph(description, normal_style))
                    
                    # Puesto y fechas
                    position = exp.get('position', '')
                    start_date = exp.get('startDate', '')
                    end_date = exp.get('endDate', '')
                    current = exp.get('current', False)
                    
                    if position:
                        date_text = CVPDFGenerator._format_date_range(start_date, end_date, current)
                        position_line = f"{position} - {date_text}"
                        story.append(Paragraph(position_line, position_style))
                    
                    # Logros organizados
                    sections = exp.get('sections', [])
                    if sections:
                        for section in sections:
                            section_title = section.get('title', '')
                            if section_title:
                                story.append(Paragraph(section_title, company_style))
                            
                            achievements = section.get('achievements', [])
                            for achievement in achievements:
                                story.append(Paragraph(f"• {achievement}", bullet_style))
                    else:
                        # Logros simples
                        achievements = exp.get('achievements', [])
                        for achievement in achievements:
                            story.append(Paragraph(f"• {achievement}", bullet_style))
                    
                    # Tecnologías
                    technologies = exp.get('technologies', [])
                    if technologies:
                        tech_text = f"Tecnologías: {CVPDFGenerator._format_technologies(technologies)}"
                        story.append(Paragraph(tech_text, normal_style))
                    
                    story.append(Spacer(1, 8))
                
                # Proyectos Destacados
                if projects:
                    story.append(Paragraph('Proyectos Destacados', company_style))
                    
                    for project in projects:
                        # Nombre del proyecto y fechas
                        name = project.get('name', '')
                        start_date = project.get('startDate', '')
                        end_date = project.get('endDate', '')
                        current = project.get('current', False)
                        
                        if name:
                            date_text = CVPDFGenerator._format_date_range(start_date, end_date, current, project=True)
                            project_line = f"{name} - {date_text}"
                            story.append(Paragraph(project_line, position_style))
                        
                        # URL del proyecto
                        url = project.get('url', '')
                        if url:
                            story.append(Paragraph(f"Ver proyecto: {url}", normal_style))
                        
                        # Descripción
                        description = project.get('description', '')
                        if description:
                            story.append(Paragraph(description, normal_style))
                        
                        # Highlights
                        highlights = project.get('highlights', [])
                        for highlight in highlights:
                            story.append(Paragraph(f"• {highlight}", bullet_style))
                        
                        # Tecnologías
                        technologies = project.get('technologies', [])
                        if technologies:
                            tech_text = f"Tecnologías: {CVPDFGenerator._format_technologies(technologies)}"
                            story.append(Paragraph(tech_text, normal_style))
                        
                        story.append(Spacer(1, 6))
            
            # 5. EDUCACIÓN
            education = cv_data.get('education', [])
            if education:
                story.append(Paragraph('Educación', section_style))
                
                for edu in education:
                    institution = edu.get('institution', '')
                    field_of_study = edu.get('fieldOfStudy', '')
                    start_date = edu.get('startDate', '')
                    end_date = edu.get('endDate', '')
                    current = edu.get('current', False)
                    
                    # Institución y campo de estudio
                    edu_text = institution
                    if field_of_study:
                        edu_text += f" — {field_of_study}"
                    
                    date_text = CVPDFGenerator._format_date_range(start_date, end_date, current)
                    edu_line = f"{edu_text} - {date_text}"
                    story.append(Paragraph(edu_line, position_style))
                    
                    # Logros de educación
                    achievements = edu.get('achievements', [])
                    for achievement in achievements:
                        story.append(Paragraph(f"• {achievement}", bullet_style))
                    
                    story.append(Spacer(1, 6))
            
            # 6. HABILIDADES Y CERTIFICACIONES
            skills = cv_data.get('skills', [])
            certifications = cv_data.get('certifications', [])
            hobbies = cv_data.get('hobbies', [])
            languages = cv_data.get('languages', [])
            
            if skills or certifications or hobbies or languages:
                story.append(Paragraph('Habilidades & Certificaciones', section_style))
                
                # Organizar habilidades
                skills_organized = CVPDFGenerator._organize_skills(skills)
                
                # Software
                if skills_organized['software']:
                    software_text = CVPDFGenerator._format_skills_text(skills_organized['software'])
                    story.append(Paragraph(f"Software: {software_text}", normal_style))
                
                # Gestión de proyectos
                if skills_organized['projectManagement']:
                    management_text = CVPDFGenerator._format_skills_text(skills_organized['projectManagement'])
                    story.append(Paragraph(f"Gestión de Proyectos: {management_text}", normal_style))
                
                # Certificaciones
                if certifications:
                    cert_text = CVPDFGenerator._format_certifications_text(certifications)
                    story.append(Paragraph(f"Certificaciones: {cert_text}", normal_style))
                
                # Idiomas
                all_languages = []
                if languages:
                    all_languages.extend([f"{lang.get('language', '')} ({lang.get('proficiency', '')})" for lang in languages])
                if skills_organized['languages']:
                    all_languages.extend([f"{skill.get('name', '')} ({skill.get('level', '')})" for skill in skills_organized['languages']])
                
                if all_languages:
                    lang_text = ', '.join(all_languages)
                    story.append(Paragraph(f"Idiomas: {lang_text}", normal_style))
                
                # Hobbies
                if hobbies:
                    hobbies_text = ', '.join(hobbies)
                    story.append(Paragraph(f"Hobbies: {hobbies_text}", normal_style))
                
                # Otras competencias
                if skills_organized['other']:
                    other_text = CVPDFGenerator._format_skills_text(skills_organized['other'])
                    story.append(Paragraph(f"Otras Competencias: {other_text}", normal_style))
            
            # Generar PDF
            doc.build(story)
            
            # Obtener contenido del PDF
            pdf_content = buffer.getvalue()
            buffer.close()
            
            # Generar nombre del archivo
            file_name = f"CV_{full_name.replace(' ', '_')}.pdf" if full_name else "CV.pdf"
            
            return pdf_content, file_name
            
        except Exception as e:
            print(f"❌ Error generando PDF: {e}")
            raise Exception(f"Error al generar PDF: {str(e)}")
    
    @staticmethod
    def _format_date_range(start_date: str, end_date: str, current: bool, project: bool = False) -> str:
        """Formatea un rango de fechas"""
        if not start_date:
            return ""
        
        start_formatted = CVPDFGenerator._format_date(start_date)
        
        if current:
            return f"{start_formatted} – {'En curso' if project else 'Actualidad'}"
        elif end_date:
            end_formatted = CVPDFGenerator._format_date(end_date)
            return f"{start_formatted} – {end_formatted}"
        else:
            return start_formatted
    
    @staticmethod
    def _format_date(date_string: str) -> str:
        """Formatea una fecha"""
        if not date_string:
            return ""
        
        try:
            # Si el formato es YYYY-MM o YYYY-MM-DD, mostrar solo mes/año
            if re.match(r'^\d{4}-\d{2}', date_string):
                year, month = date_string.split('-')[:2]
                return f"{month}/{year}"
            # Si el formato es solo YYYY
            elif re.match(r'^\d{4}$', date_string):
                return date_string
            else:
                return date_string
        except:
            return date_string
    
    @staticmethod
    def _organize_skills(skills: list) -> Dict[str, list]:
        """Organiza las habilidades por categoría"""
        software = [skill for skill in skills if skill.get('category') == 'Technical']
        project_management = [skill for skill in skills if skill.get('category') in ['Leadership', 'Analytical']]
        languages = [skill for skill in skills if skill.get('category') == 'Language']
        other = [skill for skill in skills if skill.get('category') in ['Research', 'Communication']]
        
        return {
            'software': software,
            'projectManagement': project_management,
            'languages': languages,
            'other': other
        }
    
    @staticmethod
    def _format_skills_text(skills: list) -> str:
        """Formatea texto de habilidades"""
        formatted_skills = []
        for skill in skills:
            name = skill.get('name', '')
            level = skill.get('level', '')
            if level and level != 'Proficiente':
                formatted_skills.append(f"{name} ({level})")
            else:
                formatted_skills.append(name)
        return ', '.join(formatted_skills)
    
    @staticmethod
    def _format_certifications_text(certifications: list) -> str:
        """Formatea texto de certificaciones"""
        formatted_certs = []
        for cert in certifications:
            cert_text = cert.get('name', '')
            issuer = cert.get('issuer', '')
            date = cert.get('date', '')
            
            if issuer:
                cert_text += f" - {issuer}"
            if date:
                cert_text += f" ({CVPDFGenerator._format_date(date)})"
            
            formatted_certs.append(cert_text)
        return ', '.join(formatted_certs)
