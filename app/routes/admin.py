"""
CIS School System - Admin Routes
==================================
Admin-only pages:
  - Manage teachers (create, edit, assign streams)
  - Manage students (add, edit, import from Excel)
  - Open / close assessments
  - View class completion status
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash
from ..models import db, Teacher, Student, Grade, Stream, Term, Assessment, Mark, ReportCard
from ..models import get_subjects
from .auth import login_required, role_required

admin_bp = Blueprint("admin", __name__)


# ---------------------------------------------------------------------------
# OVERVIEW
# ---------------------------------------------------------------------------

@admin_bp.route("/")
@login_required
@role_required("admin", "principal")
def index():
    """Admin home — shows all grades with mark completion status"""
    active_term = Term.query.filter_by(is_active=True).first()
    grades      = Grade.query.order_by(Grade.sort_order).all()
    assessments = []

    completion = {}   # { stream_id: { assessment_id: { entered, total } } }

    if active_term:
        assessments = Assessment.query.filter_by(term_id=active_term.id).order_by(Assessment.number).all()

        for grade in grades:
            for stream in grade.streams:
                student_count = Student.query.filter_by(stream_id=stream.id, is_active=True).count()
                completion[stream.id] = {}

                for ass in assessments:
                    marked = (
                        db.session.query(Mark.student_id)
                        .filter_by(assessment_id=ass.id)
                        .filter(Mark.student_id.in_(
                            db.session.query(Student.id).filter_by(stream_id=stream.id, is_active=True)
                        ))
                        .distinct()
                        .count()
                    )
                    completion[stream.id][ass.id] = {
                        "entered": marked,
                        "total":   student_count,
                        "pct":     round((marked / student_count * 100) if student_count else 0),
                    }

    return render_template(
        "admin/index.html",
        grades=grades,
        assessments=assessments,
        active_term=active_term,
        completion=completion,
    )


# ---------------------------------------------------------------------------
# ASSESSMENT MANAGEMENT
# ---------------------------------------------------------------------------

@admin_bp.route("/assessment/<int:assessment_id>/toggle", methods=["POST"])
@login_required
@role_required("admin", "principal")
def toggle_assessment(assessment_id):
    """Open or close an assessment for mark entry"""
    assessment = Assessment.query.get_or_404(assessment_id)
    assessment.is_open = not assessment.is_open
    db.session.commit()
    status = "opened" if assessment.is_open else "closed"
    flash(f"Assessment '{assessment.name}' has been {status}.", "success")
    return redirect(url_for("admin.index"))


# ---------------------------------------------------------------------------
# TEACHER MANAGEMENT
# ---------------------------------------------------------------------------

@admin_bp.route("/teachers")
@login_required
@role_required("admin", "principal")
def teachers():
    all_teachers = Teacher.query.order_by(Teacher.full_name).all()
    streams      = Stream.query.join(Grade).order_by(Grade.sort_order).all()
    return render_template("admin/teachers.html", teachers=all_teachers, streams=streams)


@admin_bp.route("/teachers/add", methods=["POST"])
@login_required
@role_required("admin", "principal")
def add_teacher():
    name      = request.form.get("full_name", "").strip()
    email     = request.form.get("email", "").strip().lower()
    role      = request.form.get("role", "teacher")
    stream_id = request.form.get("stream_id") or None
    password  = request.form.get("password", "teacher123")

    if Teacher.query.filter_by(email=email).first():
        flash(f"A teacher with email {email} already exists.", "danger")
        return redirect(url_for("admin.teachers"))

    teacher = Teacher(
        full_name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        stream_id=int(stream_id) if stream_id else None,
    )
    db.session.add(teacher)
    db.session.commit()
    flash(f"Teacher '{name}' added. Default password: {password}", "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/<int:teacher_id>/edit", methods=["POST"])
@login_required
@role_required("admin", "principal")
def edit_teacher(teacher_id):
    teacher   = Teacher.query.get_or_404(teacher_id)
    teacher.full_name = request.form.get("full_name", teacher.full_name).strip()
    teacher.role      = request.form.get("role", teacher.role)
    stream_id         = request.form.get("stream_id") or None
    teacher.stream_id = int(stream_id) if stream_id else None
    new_pw            = request.form.get("new_password", "").strip()
    if new_pw:
        teacher.password_hash = generate_password_hash(new_pw)
    db.session.commit()
    flash(f"Teacher '{teacher.full_name}' updated.", "success")
    return redirect(url_for("admin.teachers"))


# ---------------------------------------------------------------------------
# STUDENT MANAGEMENT
# ---------------------------------------------------------------------------

@admin_bp.route("/students")
@login_required
@role_required("admin", "principal")
def students():
    grade_id  = request.args.get("grade_id", type=int)
    stream_id = request.args.get("stream_id", type=int)

    query = Student.query.filter_by(is_active=True)
    if stream_id:
        query = query.filter_by(stream_id=stream_id)
    elif grade_id:
        stream_ids = [s.id for s in Stream.query.filter_by(grade_id=grade_id).all()]
        query = query.filter(Student.stream_id.in_(stream_ids))

    all_students = query.order_by(Student.full_name).all()
    grades       = Grade.query.order_by(Grade.sort_order).all()
    streams      = Stream.query.join(Grade).order_by(Grade.sort_order).all()

    return render_template(
        "admin/students.html",
        students=all_students,
        grades=grades,
        streams=streams,
        selected_grade=grade_id,
        selected_stream=stream_id,
    )


@admin_bp.route("/students/add", methods=["POST"])
@login_required
@role_required("admin", "principal")
def add_student():
    name        = request.form.get("full_name", "").strip()
    adm_no      = request.form.get("admission_no", "").strip()
    grade_id    = int(request.form.get("grade_id"))
    stream_id   = request.form.get("stream_id") or None
    gender      = request.form.get("gender", "")
    parent_email = request.form.get("parent_email", "").strip() or None

    if Student.query.filter_by(admission_no=adm_no).first():
        flash(f"Admission number {adm_no} already exists.", "danger")
        return redirect(url_for("admin.students"))

    student = Student(
        full_name=name,
        admission_no=adm_no,
        grade_id=grade_id,
        stream_id=int(stream_id) if stream_id else None,
        gender=gender,
        parent_email=parent_email,
    )
    db.session.add(student)
    db.session.commit()
    flash(f"Student '{name}' added successfully.", "success")
    return redirect(url_for("admin.students"))


@admin_bp.route("/students/import", methods=["POST"])
@login_required
@role_required("admin", "principal")
def import_students():
    """
    Import students from an uploaded Excel file.
    Expected columns: Name, Admission No, Grade, Stream, Gender, Parent Email
    """
    import pandas as pd
    from io import BytesIO

    file = request.files.get("excel_file")
    if not file:
        flash("No file uploaded.", "danger")
        return redirect(url_for("admin.students"))

    try:
        df = pd.read_excel(BytesIO(file.read()))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        added   = 0
        skipped = 0

        for _, row in df.iterrows():
            name     = str(row.get("name", "")).strip()
            adm_no   = str(row.get("admission_no", "")).strip()
            grade_nm = str(row.get("grade", "")).strip()
            stream_nm = str(row.get("stream", "")).strip().upper()

            if not name or not adm_no:
                skipped += 1
                continue

            if Student.query.filter_by(admission_no=adm_no).first():
                skipped += 1
                continue

            grade  = Grade.query.filter_by(name=grade_nm).first()
            stream = Stream.query.filter_by(name=stream_nm, grade_id=grade.id).first() if grade else None

            if not grade:
                skipped += 1
                continue

            student = Student(
                full_name=name,
                admission_no=adm_no,
                grade_id=grade.id,
                stream_id=stream.id if stream else None,
                gender=str(row.get("gender", "")).strip(),
                parent_email=str(row.get("parent_email", "")).strip() or None,
            )
            db.session.add(student)
            added += 1

        db.session.commit()
        flash(f"Import complete — {added} students added, {skipped} skipped.", "success")

    except Exception as e:
        flash(f"Import failed: {str(e)}", "danger")

    return redirect(url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/edit-name", methods=["POST"])
@login_required
@role_required("admin", "principal", "teacher")
def edit_student_name(student_id):
    """Fix a spelling error in a student's name."""
    student = Student.query.get_or_404(student_id)
    new_name = request.form.get("full_name", "").strip()
    if new_name and len(new_name) >= 2:
        old_name = student.full_name
        student.full_name = new_name
        db.session.commit()
        flash(f"Name updated: '{old_name}' → '{new_name}'", "success")
    else:
        flash("Name too short — not updated.", "warning")
    # Go back to wherever the request came from
    return redirect(request.referrer or url_for("admin.students"))


@admin_bp.route("/term/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "principal")
def edit_term():
    """Edit the active term dates — these appear on every report card."""
    from datetime import datetime
    active_term = Term.query.filter_by(is_active=True).first()
    if not active_term:
        flash("No active term found.", "warning")
        return redirect(url_for("admin.index"))

    if request.method == "POST":
        def parse_date(field):
            val = request.form.get(field, "").strip()
            if val:
                try:
                    return datetime.strptime(val, "%Y-%m-%d").date()
                except ValueError:
                    return None
            return None

        active_term.open_date      = parse_date("open_date")
        active_term.close_date     = parse_date("close_date")
        active_term.next_term_date = parse_date("next_term_date")

        # Also update term number and year if changed
        term_num = request.form.get("term_number", "").strip()
        if term_num.isdigit():
            active_term.term_number = int(term_num)

        db.session.commit()
        flash("Term dates updated — all new PDFs will use these dates.", "success")
        return redirect(url_for("admin.edit_term"))

    return render_template("admin/edit_term.html", term=active_term)


@admin_bp.route("/streams")
@login_required
@role_required("admin", "principal")
def streams():
    """Manage streams per grade — add or remove streams"""
    grades  = Grade.query.order_by(Grade.sort_order).all()
    streams = Stream.query.join(Grade).order_by(Grade.sort_order).all()
    return render_template("admin/streams.html", grades=grades, streams=streams)


@admin_bp.route("/streams/add", methods=["POST"])
@login_required
@role_required("admin", "principal")
def add_stream():
    grade_id    = int(request.form.get("grade_id"))
    stream_name = request.form.get("stream_name", "").strip().upper()
    if not stream_name:
        flash("Stream name cannot be empty.", "danger")
        return redirect(url_for("admin.streams"))
    existing = Stream.query.filter_by(grade_id=grade_id, name=stream_name).first()
    if existing:
        flash(f"Stream {stream_name} already exists for this grade.", "warning")
        return redirect(url_for("admin.streams"))
    stream = Stream(grade_id=grade_id, name=stream_name)
    db.session.add(stream)
    db.session.commit()
    grade = Grade.query.get(grade_id)
    flash(f"Stream {grade.name} {stream_name} added.", "success")
    return redirect(url_for("admin.streams"))


@admin_bp.route("/streams/<int:stream_id>/delete", methods=["POST"])
@login_required
@role_required("admin", "principal")
def delete_stream(stream_id):
    stream = Stream.query.get_or_404(stream_id)
    student_count = Student.query.filter_by(stream_id=stream_id).count()
    if student_count > 0:
        flash(f"Cannot delete — {student_count} students are assigned to {stream.grade.name} {stream.name}. Move them first.", "danger")
        return redirect(url_for("admin.streams"))
    name = f"{stream.grade.name} {stream.name}"
    db.session.delete(stream)
    db.session.commit()
    flash(f"Stream {name} deleted.", "success")
    return redirect(url_for("admin.streams"))


@admin_bp.route("/streams/<int:stream_id>/rename", methods=["POST"])
@login_required
@role_required("admin", "principal")
def rename_stream(stream_id):
    stream   = Stream.query.get_or_404(stream_id)
    new_name = request.form.get("new_name", "").strip().upper()
    if not new_name:
        flash("Name cannot be empty.", "danger")
        return redirect(url_for("admin.streams"))
    stream.name = new_name
    db.session.commit()
    flash(f"Stream renamed to {stream.grade.name} {new_name}.", "success")
    return redirect(url_for("admin.streams"))
