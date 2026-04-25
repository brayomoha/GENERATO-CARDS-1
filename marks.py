"""
CIS School System - Marks Entry Routes
========================================
Teachers use these pages to enter subject marks for their class.
Handles both single-paper and split-paper (English/Kiswahili) subjects.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from ..models import db, Teacher, Student, Grade, Stream, Assessment, Mark, Term
from ..models import get_subjects, get_split_subjects, calculate_grade_band
from ..grading import combine_split_subject, assign_performance_level
from .auth import login_required

marks_bp = Blueprint("marks", __name__)


@marks_bp.route("/")
@login_required
def index():
    """List all grade/stream/assessment combinations the teacher can enter marks for"""
    teacher = Teacher.query.get(session["teacher_id"])
    active_term = Term.query.filter_by(is_active=True).first()

    if not active_term:
        flash("No active term found. Contact admin.", "warning")
        return redirect(url_for("main.dashboard"))

    open_assessments = Assessment.query.filter_by(term_id=active_term.id, is_open=True).all()

    # Admins and principals can see all grades
    if teacher.role in ("admin", "principal"):
        grades = Grade.query.order_by(Grade.sort_order).all()
        streams = Stream.query.all()
    else:
        # Regular teachers only see their assigned stream
        if not teacher.stream_id:
            flash("You are not assigned to any class. Contact admin.", "warning")
            return redirect(url_for("main.dashboard"))
        grades  = [teacher.stream.grade]
        streams = [teacher.stream]

    return render_template(
        "marks/index.html",
        teacher=teacher,
        grades=grades,
        streams=streams,
        open_assessments=open_assessments,
        active_term=active_term,
    )


@marks_bp.route("/enter/<int:assessment_id>/<int:stream_id>")
@login_required
def enter_marks(assessment_id, stream_id):
    """Show the mark entry sheet for a specific assessment and stream"""
    teacher    = Teacher.query.get(session["teacher_id"])
    assessment = Assessment.query.get_or_404(assessment_id)
    stream     = Stream.query.get_or_404(stream_id)
    grade      = stream.grade

    # Security: non-admin teachers can only enter marks for their own stream
    if teacher.role not in ("admin", "principal") and teacher.stream_id != stream_id:
        flash("You can only enter marks for your assigned class.", "danger")
        return redirect(url_for("marks.index"))

    if not assessment.is_open:
        flash("This assessment is not open for mark entry.", "warning")
        return redirect(url_for("marks.index"))

    students = (
        Student.query
        .filter_by(stream_id=stream_id, is_active=True)
        .order_by(Student.full_name)
        .all()
    )

    subjects      = get_subjects(grade.name)
    split_subjects = get_split_subjects(grade.name)

    # Load existing marks for this assessment + stream
    student_ids = [s.id for s in students]
    existing_marks = (
        Mark.query
        .filter(
            Mark.assessment_id == assessment_id,
            Mark.student_id.in_(student_ids)
        )
        .all()
    )

    # Build a lookup: { student_id: { subject: Mark } }
    marks_lookup = {}
    for mark in existing_marks:
        marks_lookup.setdefault(mark.student_id, {})[mark.subject] = mark

    return render_template(
        "marks/enter.html",
        teacher=teacher,
        assessment=assessment,
        stream=stream,
        grade=grade,
        students=students,
        subjects=subjects,
        split_subjects=split_subjects,
        marks_lookup=marks_lookup,
    )


@marks_bp.route("/save", methods=["POST"])
@login_required
def save_marks():
    """
    Save submitted marks to the database.
    Called when teacher submits the mark entry form.
    Handles both single-paper and split-paper subjects.
    """
    teacher       = Teacher.query.get(session["teacher_id"])
    assessment_id = int(request.form.get("assessment_id"))
    stream_id     = int(request.form.get("stream_id"))
    assessment    = Assessment.query.get_or_404(assessment_id)
    stream        = Stream.query.get_or_404(stream_id)
    grade         = stream.grade

    if teacher.role not in ("admin", "principal") and teacher.stream_id != stream_id:
        flash("Permission denied.", "danger")
        return redirect(url_for("marks.index"))

    if not assessment.is_open:
        flash("This assessment is closed.", "warning")
        return redirect(url_for("marks.index"))

    subjects       = get_subjects(grade.name)
    split_subjects = get_split_subjects(grade.name)

    students = Student.query.filter_by(stream_id=stream_id, is_active=True).all()
    saved    = 0

    for student in students:
        for subject in subjects:
            # Build form field key (spaces replaced with underscores for HTML)
            field_key = f"{student.id}_{subject.replace(' ', '_').replace('&', 'and')}"

            if subject in split_subjects:
                p1_max_val, p2_max_val = split_subjects[subject][1], split_subjects[subject][3]
                p1_val = request.form.get(f"{field_key}_p1", "").strip()
                p2_val = request.form.get(f"{field_key}_p2", "").strip()

                paper1 = float(p1_val) if p1_val else None
                paper2 = float(p2_val) if p2_val else None
                combined = combine_split_subject(paper1, paper2, p1_max_val, p2_max_val) if paper1 is not None and paper2 is not None else None

                effective = combined
            else:
                raw = request.form.get(field_key, "").strip()
                score    = float(raw) if raw else None
                paper1   = None
                paper2   = None
                combined = None
                effective = score

            # Grade band
            if effective is not None:
                code, label = assign_performance_level(effective, grade.name)
            else:
                code, label = None, None

            # Upsert — update if exists, insert if not
            mark = Mark.query.filter_by(
                student_id=student.id,
                assessment_id=assessment_id,
                subject=subject,
            ).first()

            if mark is None:
                mark = Mark(
                    student_id=student.id,
                    assessment_id=assessment_id,
                    subject=subject,
                    entered_by=teacher.id,
                )
                db.session.add(mark)

            if subject in split_subjects:
                mark.paper1_score   = paper1
                mark.paper2_score   = paper2
                mark.combined_score = combined
                mark.score          = None
            else:
                mark.score          = effective
                mark.paper1_score   = None
                mark.paper2_score   = None
                mark.combined_score = None

            mark.grade_code  = code
            mark.grade_label = label
            saved += 1

    db.session.commit()
    flash(f"✅ Marks saved successfully for {stream.grade.name} {stream.name} — {assessment.name}.", "success")
    return redirect(url_for("marks.enter_marks", assessment_id=assessment_id, stream_id=stream_id))


@marks_bp.route("/api/student/<int:student_id>/marks/<int:assessment_id>")
@login_required
def get_student_marks(student_id, assessment_id):
    """API endpoint — returns marks for one student as JSON (used by dashboard widgets)"""
    marks = Mark.query.filter_by(student_id=student_id, assessment_id=assessment_id).all()
    return jsonify([
        {
            "subject":         m.subject,
            "score":           m.score,
            "paper1":          m.paper1_score,
            "paper2":          m.paper2_score,
            "combined":        m.combined_score,
            "grade_code":      m.grade_code,
            "grade_label":     m.grade_label,
        }
        for m in marks
    ])
