#!/bin/bash
echo "==> Running database setup..."
python3 -c "
from app import create_app
from app.models import db, Grade, Stream, AcademicYear, Term, Assessment, Teacher
from app.comments_bank import CommentTemplate, seed_comment_templates
from werkzeug.security import generate_password_hash
from datetime import date

app = create_app()
with app.app_context():
    db.create_all()

    # Grades
    from app.models import GRADE_LEVELS
    grade_defs = [
        ('Reception','reception',1),('PP1','preschool',2),('PP2','preschool',3),
        ('Grade 1','lower_primary',4),('Grade 2','lower_primary',5),('Grade 3','lower_primary',6),
        ('Grade 4','upper_primary',7),('Grade 5','upper_primary',8),('Grade 6','upper_primary',9),
        ('Grade 7','junior',10),('Grade 8','junior',11),('Grade 9','junior',12),
    ]
    for name, level, order in grade_defs:
        if not Grade.query.filter_by(name=name).first():
            g = Grade(name=name, level_group=level, sort_order=order)
            db.session.add(g)
            db.session.flush()
            db.session.add(Stream(grade_id=g.id, name='RED'))
            db.session.add(Stream(grade_id=g.id, name='YELLOW'))

    # Academic year and term
    yr = AcademicYear.query.filter_by(year=2026).first()
    if not yr:
        yr = AcademicYear(year=2026, is_active=True)
        db.session.add(yr)
        db.session.flush()

    t1 = Term.query.filter_by(academic_year_id=yr.id, term_number=1).first()
    if not t1:
        t1 = Term(academic_year_id=yr.id, term_number=1, is_active=True,
                  open_date=date(2026,1,6), close_date=date(2026,3,31), next_term_date=date(2026,5,4))
        db.session.add(t1)
        db.session.flush()
        for num, name, open_d in [(1,'Entry Assessment',True),(2,'Mid Term',True),(3,'End Term',False)]:
            db.session.add(Assessment(term_id=t1.id, name=name, number=num, is_open=open_d))

    # Admin accounts
    for full_name, email, pwd, role in [
        ('CIS Administrator','admin@cis.ac.ke','admin123','admin'),
        ('CIS Principal','principal@cis.ac.ke','principal123','principal'),
    ]:
        if not Teacher.query.filter_by(email=email).first():
            db.session.add(Teacher(
                full_name=full_name, email=email,
                password_hash=generate_password_hash(pwd, method='pbkdf2:sha256'),
                role=role
            ))

    db.session.commit()
    print('Database ready')

    # Seed comments
    seed_comment_templates(app)
"
echo "==> Starting server..."
exec gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --timeout 120
