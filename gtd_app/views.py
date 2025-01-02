from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Q, F
from django.views.decorators.http import require_http_methods
import csv
import json
from .models import InboxItem, SingleTask, Project, ProjectTask, Retrospective, Sprint
from django.db import transaction

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {username}!")
                return redirect('home')
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful!")
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required
def home_view(request):
    if request.method == 'POST':
        text = request.POST.get('thought')
        if text:
            InboxItem.objects.create(
                user=request.user,
                text=text
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success'})
            messages.success(request, "Thought captured!")
            return redirect('home')
    
    recent_items = InboxItem.objects.filter(
        user=request.user,
        processed=False
    ).order_by('-created_at')[:5]
    
    return render(request, 'gtd_app/home.html', {
        'recent_items': recent_items
    })

@login_required
def inbox_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        item_id = request.POST.get('item_id')
        item = get_object_or_404(InboxItem, id=item_id, user=request.user)

        if action == 'do_it_now':
            item.processed = True
            item.processed_at = timezone.now()
            item.archive_category = 'quick_wins'
            item.save()
            messages.success(request, "Item marked as done!")

        elif action == 'eliminate':
            item.processed = True
            item.processed_at = timezone.now()
            item.eliminated = True
            item.save()
            messages.success(request, "Item eliminated!")

        elif action == 'convert_to_task':
            # Convert estimated time to weeks
            estimated_weeks = convert_to_weeks(request.POST.get('estimated_time', ''))
            
            SingleTask.objects.create(
                user=request.user,
                title=request.POST.get('title', item.text),
                description=item.text,
                cost=int(request.POST.get('cost', 1)),
                benefit=int(request.POST.get('benefit', 1)),
                estimated_time=estimated_weeks,
                category=request.POST.get('category', '')
            )
            item.processed = True
            item.processed_at = timezone.now()
            item.save()
            messages.success(request, "Converted to task!")

        elif action == 'convert_to_project':
            # Convert estimated time to weeks
            estimated_weeks = convert_to_weeks(request.POST.get('estimated_time', ''))
            
            Project.objects.create(
                user=request.user,
                title=request.POST.get('title', item.text),
                description=item.text,
                cost=int(request.POST.get('cost', 1)),
                benefit=int(request.POST.get('benefit', 1)),
                estimated_time=estimated_weeks,
                category=request.POST.get('category', '')
            )
            item.processed = True
            item.processed_at = timezone.now()
            item.save()
            messages.success(request, "Converted to project!")

        return redirect('inbox')

    inbox_items = InboxItem.objects.filter(
        user=request.user,
        processed=False
    ).order_by('-created_at')

    return render(request, 'gtd_app/inbox.html', {
        'inbox_items': inbox_items
    })

def convert_to_weeks(time_str):
    """Convert various time formats to weeks (float)"""
    if not time_str:
        return 0.0
    
    # If already in weeks format
    if isinstance(time_str, (int, float)):
        return float(time_str)
    
    time_str = time_str.lower().strip()
    
    # Parse "X weeks" format
    if 'week' in time_str:
        return float(time_str.split()[0])
    
    # Parse "X days" format
    if 'day' in time_str:
        days = float(time_str.split()[0])
        return round(days / 7, 1)
    
    # Parse "Xh" or "X hours" format
    if 'h' in time_str or 'hour' in time_str:
        hours = float(''.join(c for c in time_str if c.isdigit() or c == '.'))
        return round(hours / (7 * 8), 1)  # Assuming 8-hour workdays
    
    # Parse "Xm" or "X minutes" format
    if 'm' in time_str or 'minute' in time_str:
        minutes = float(''.join(c for c in time_str if c.isdigit() or c == '.'))
        return round(minutes / (7 * 8 * 60), 1)  # Assuming 8-hour workdays
    
    return 0.0

def calculate_efficiency_score(benefit, cost):
    """
    Calculate efficiency score using a non-linear formula that emphasizes high benefit and low cost.
    The formula: (benefit^2) / (cost + 1)
    This gives more weight to high-benefit tasks and penalizes high-cost tasks less severely.
    The +1 in denominator prevents division by zero and maintains a reasonable scale.
    """
    return round((benefit ** 2) / (cost + 1), 2)

@login_required
def backlog_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'move_to_sprint':
            item_id = request.POST.get('item_id')
            item_type = request.POST.get('item_type', 'task')
            
            # Get active sprint or create new one
            active_sprint = Sprint.objects.filter(
                user=request.user,
                status='active'
            ).first()
            
            if not active_sprint:
                active_sprint = Sprint.objects.create(
                    user=request.user,
                    start_date=timezone.now()
                )
            
            # Get the appropriate model instance
            if item_type == 'project_task':
                item = get_object_or_404(ProjectTask, id=item_id, project__user=request.user)
            else:
                item = get_object_or_404(SingleTask, id=item_id, user=request.user)
            
            # Move to sprint
            item.sprint = active_sprint
            item.status = 'todo'
            item.save()
            messages.success(request, f"{item.title} moved to sprint!")
            
        elif action == 'edit_item':
            item_id = request.POST.get('item_id')
            item_type = request.POST.get('item_type', 'task')
            
            if item_type == 'project':
                item = get_object_or_404(Project, id=item_id, user=request.user)
            else:
                item = get_object_or_404(SingleTask, id=item_id, user=request.user)
            
            # Update fields
            item.title = request.POST.get('title')
            item.cost = int(request.POST.get('cost', 1))
            item.benefit = int(request.POST.get('benefit', 1))
            item.category = request.POST.get('category')
            
            # Convert estimated time to weeks
            estimated_weeks = convert_to_weeks(request.POST.get('estimated_time', ''))
            item.estimated_time = estimated_weeks
            
            if item_type == 'project':
                # Update all project tasks with new values
                ProjectTask.objects.filter(project=item).update(
                    cost=item.cost,
                    benefit=item.benefit,
                    category=item.category,
                    estimated_time=estimated_weeks
                )
            
            item.save()
            messages.success(request, f"{item.title} updated!")

        elif action == 'add_project_task':
            project_id = request.POST.get('project_id')
            project = get_object_or_404(Project, id=project_id, user=request.user)
            
            # Convert estimated time to weeks
            estimated_weeks = convert_to_weeks(request.POST.get('estimated_time', ''))
            
            # Create task inheriting project attributes
            task = ProjectTask.objects.create(
                project=project,
                user=request.user,
                title=request.POST.get('title'),
                cost=project.cost,
                benefit=project.benefit,
                category=project.category,
                estimated_time=estimated_weeks
            )
            
            messages.success(request, f"Task '{task.title}' added to project!")
            
        elif action == 'mark_complete':
            item_id = request.POST.get('item_id')
            item_type = request.POST.get('item_type')
            
            if item_type == 'project':
                item = get_object_or_404(Project, id=item_id, user=request.user)
                # Mark all project tasks as completed
                ProjectTask.objects.filter(project=item).update(
                    archived=True,
                    archived_date=timezone.now(),
                    status='done'
                )
            elif item_type == 'project_task':
                item = get_object_or_404(ProjectTask, id=item_id, project__user=request.user)
            else:
                item = get_object_or_404(SingleTask, id=item_id, user=request.user)
            
            item.archived = True
            item.archived_date = timezone.now()
            item.status = 'done'
            item.save()
            messages.success(request, f"{item.title} marked as complete!")
            
        elif action == 'delete_item':
            item_id = request.POST.get('item_id')
            item_type = request.POST.get('item_type')
            
            if item_type == 'project':
                item = get_object_or_404(Project, id=item_id, user=request.user)
                # Delete all associated tasks first
                ProjectTask.objects.filter(project=item).delete()
            elif item_type == 'project_task':
                item = get_object_or_404(ProjectTask, id=item_id, project__user=request.user)
            else:
                item = get_object_or_404(SingleTask, id=item_id, user=request.user)
            
            title = item.title
            item.delete()
            messages.success(request, f"{title} deleted successfully!")
        
        return redirect('backlog')
    
    # Get all non-archived tasks and projects
    tasks = SingleTask.objects.filter(
        user=request.user,
        archived=False,
        sprint__isnull=True
    )
    
    projects = Project.objects.filter(
        user=request.user,
        archived=False,
        sprint__isnull=True
    ).prefetch_related(
        'tasks'
    )
    
    # Combine and prepare items for display
    backlog_items = []
    
    for task in tasks:
        backlog_items.append({
            'id': task.id,
            'type': 'task',
            'title': task.title,
            'category': task.category,
            'cost': task.cost,
            'benefit': task.benefit,
            'estimated_weeks': task.estimated_time,
            'score': task.efficiency_score,
            'created_at': task.created_at
        })
    
    for project in projects:
        # Get project tasks
        project_tasks = []
        for task in project.tasks.filter(archived=False, sprint__isnull=True):
            project_tasks.append({
                'id': task.id,
                'title': task.title,
                'category': task.category,
                'cost': task.cost,
                'benefit': task.benefit,
                'estimated_weeks': task.estimated_time,
                'score': task.efficiency_score,
                'created_at': task.created_at
            })
        
        backlog_items.append({
            'id': project.id,
            'type': 'project',
            'title': project.title,
            'category': project.category,
            'cost': project.cost,
            'benefit': project.benefit,
            'estimated_weeks': project.estimated_time,
            'score': project.efficiency_score,
            'tasks': project_tasks,
            'created_at': project.created_at
        })
    
    # Sort by score in descending order
    backlog_items.sort(key=lambda x: x['score'], reverse=True)
    
    return render(request, 'gtd_app/backlog.html', {
        'backlog_items': backlog_items
    })

@login_required
@require_http_methods(["GET"])
def get_item_details(request, item_type, item_id):
    """API endpoint to get item details for editing"""
    try:
        if item_type == 'task':
            item = get_object_or_404(SingleTask, id=item_id, user=request.user)
        elif item_type == 'project_task':
            item = get_object_or_404(ProjectTask, id=item_id, project__user=request.user)
        elif item_type == 'project':
            item = get_object_or_404(Project, id=item_id, user=request.user)
        else:
            return JsonResponse({'error': 'Invalid item type'}, status=400)
        
        data = {
            'title': item.title,
            'description': item.description,
            'category': item.category
        }
        
        if hasattr(item, 'cost'):
            data.update({
                'cost': item.cost,
                'benefit': item.benefit,
                'estimated_time': item.estimated_time
            })
        
        if hasattr(item, 'deadline'):
            data['deadline'] = item.deadline.isoformat() if item.deadline else None
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def sprint_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        item_type = request.POST.get('item_type')
        item_id = request.POST.get('item_id')
        
        if action == 'move_to_backlog':
            if item_type == 'task':
                item = get_object_or_404(SingleTask, id=item_id, user=request.user)
            elif item_type == 'project_task':
                item = get_object_or_404(ProjectTask, id=item_id, project__user=request.user)
            else:
                messages.error(request, "Invalid item type!")
                return redirect('sprint')
            
            item.sprint = None
            item.status = 'todo'
            item.save()
            messages.success(request, f"{item.title} moved back to backlog!")
            
        elif action == 'update_status':
            if item_type == 'task':
                item = get_object_or_404(SingleTask, id=item_id, user=request.user)
            elif item_type == 'project_task':
                item = get_object_or_404(ProjectTask, id=item_id, project__user=request.user)
            else:
                messages.error(request, "Invalid item type!")
                return redirect('sprint')
            
            new_status = request.POST.get('status')
            if new_status in ['todo', 'in_progress', 'done']:
                item.status = new_status
                item.save()
                messages.success(request, f"{item.title} moved to {new_status}!")
            else:
                messages.error(request, "Invalid status!")
        
        return redirect('sprint')
    
    # Get active sprint or create new one
    active_sprint = Sprint.objects.filter(
        user=request.user,
        status='active'
    ).first()
    
    if not active_sprint:
        active_sprint = Sprint.objects.create(
            user=request.user,
            start_date=timezone.now()
        )
    
    # Get tasks in sprint
    tasks = list(SingleTask.objects.filter(
        user=request.user,
        sprint=active_sprint,
        archived=False
    ))
    tasks.extend(ProjectTask.objects.filter(
        project__user=request.user,
        sprint=active_sprint,
        archived=False
    ))
    
    # Organize tasks by status
    todo_tasks = [t for t in tasks if t.status == 'todo']
    in_progress_tasks = [t for t in tasks if t.status == 'in_progress']
    done_tasks = [t for t in tasks if t.status == 'done']
    
    return render(request, 'gtd_app/sprint.html', {
        'sprint': active_sprint,
        'todo_tasks': todo_tasks,
        'in_progress_tasks': in_progress_tasks,
        'done_tasks': done_tasks
    })

def get_active_sprint(user):
    """Helper function to get the active sprint for a user"""
    return Sprint.objects.filter(
        user=user,
        status='active'
    ).first()

@login_required
def retrospective_view(request):
    active_sprint = get_active_sprint(request.user)
    past_retrospectives = Retrospective.objects.filter(
        sprint__user=request.user
    ).select_related('sprint').order_by('-sprint__start_date')
    
    context = {
        'active_sprint': active_sprint,
        'past_retrospectives': past_retrospectives
    }
    
    if active_sprint:
        # Get all tasks in the sprint (both single tasks and project tasks)
        single_tasks = SingleTask.objects.filter(sprint=active_sprint)
        project_tasks = ProjectTask.objects.filter(sprint=active_sprint)
        
        # Combine all tasks
        sprint_tasks = list(single_tasks) + list(project_tasks)
        completed_tasks = [t for t in sprint_tasks if t.status == 'done']
        
        # Calculate sprint analytics
        total_tasks = len(sprint_tasks)
        completed_count = len(completed_tasks)
        todo_count = len([t for t in sprint_tasks if t.status == 'todo'])
        in_progress_count = len([t for t in sprint_tasks if t.status == 'in_progress'])
        
        # Calculate completion rate
        completion_rate = round((completed_count / total_tasks * 100) if total_tasks > 0 else 0, 1)
        
        # Calculate average efficiency
        efficiency_scores = [
            calculate_efficiency_score(task.benefit, task.cost)
            for task in completed_tasks
        ]
        avg_efficiency = round(
            sum(efficiency_scores) / len(efficiency_scores)
            if efficiency_scores else 0,
            2
        )
        
        # Get tasks by category
        categories = {}
        for task in sprint_tasks:
            if task.category not in categories:
                categories[task.category] = {'total': 0, 'completed': 0}
            categories[task.category]['total'] += 1
            if task.status == 'done':
                categories[task.category]['completed'] += 1
        
        # Calculate days remaining
        days_remaining = (
            active_sprint.end_date - timezone.now().date()
        ).days if active_sprint.end_date else 0
        
        sprint_analytics = {
            'total_tasks': total_tasks,
            'completed_tasks': completed_count,
            'todo_tasks': todo_count,
            'in_progress_tasks': in_progress_count,
            'completion_rate': completion_rate,
            'average_efficiency': avg_efficiency,
            'tasks_by_category': categories,
            'start_date': active_sprint.start_date,
            'days_remaining': max(0, days_remaining)
        }
        
        context.update({
            'sprint_analytics': sprint_analytics,
            'completed_tasks': completed_tasks
        })
        
        if request.method == 'POST' and request.POST.get('action') == 'finalize_sprint':
            try:
                with transaction.atomic():
                    # Create retrospective
                    retrospective = Retrospective.objects.create(
                        sprint=active_sprint,
                        total_tasks=total_tasks,
                        completed_tasks=completed_count,
                        completion_rate=completion_rate,
                        average_efficiency=avg_efficiency,
                        achievements=request.POST.get('achievements', ''),
                        challenges=request.POST.get('challenges', ''),
                        action_items=request.POST.get('action_items', '')
                    )
                    
                    # Archive all tasks
                    single_tasks.update(
                        archived=True,
                        archived_date=timezone.now()
                    )
                    project_tasks.update(
                        archived=True,
                        archived_date=timezone.now()
                    )
                    
                    # Close the sprint
                    active_sprint.status = 'completed'
                    active_sprint.end_date = timezone.now().date()
                    active_sprint.save()
                    
                    messages.success(
                        request,
                        'Sprint finalized successfully. All tasks have been archived.'
                    )
                    return redirect('retrospective')
                    
            except Exception as e:
                messages.error(
                    request,
                    f'Error finalizing sprint: {str(e)}'
                )
    
    return render(request, 'gtd_app/retrospective.html', context)

@login_required
def archives_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'reset_data':
            try:
                with transaction.atomic():
                    # Delete all user's data in the correct order to handle dependencies
                    # First, delete retrospectives related to user's sprints
                    Retrospective.objects.filter(sprint__user=request.user).delete()
                    # Then delete sprints
                    Sprint.objects.filter(user=request.user).delete()
                    # Delete tasks and projects
                    SingleTask.objects.filter(user=request.user).delete()
                    Project.objects.filter(user=request.user).delete()
                    # Finally delete inbox items
                    InboxItem.objects.filter(user=request.user).delete()
                    
                    messages.success(request, "All data has been reset successfully!")
            except Exception as e:
                messages.error(request, f"Error resetting data: {str(e)}")
            return redirect('archives')

    # Get filter parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    category = request.GET.get('category')
    min_priority = request.GET.get('min_priority')
    export_format = request.GET.get('export')
    
    # Base querysets
    tasks = SingleTask.objects.filter(
        user=request.user,
        archived=True
    )
    projects = Project.objects.filter(
        user=request.user,
        archived=True
    )
    eliminated_items = InboxItem.objects.filter(
        user=request.user,
        eliminated=True
    )
    quick_wins = InboxItem.objects.filter(
        user=request.user,
        processed=True,
        eliminated=False,
        archive_category='quick_wins'
    )
    
    # Apply filters
    if date_from:
        tasks = tasks.filter(archived_date__gte=date_from)
        projects = projects.filter(archived_date__gte=date_from)
        eliminated_items = eliminated_items.filter(created_at__gte=date_from)
        quick_wins = quick_wins.filter(processed_at__gte=date_from)
    
    if date_to:
        tasks = tasks.filter(archived_date__lte=date_to)
        projects = projects.filter(archived_date__lte=date_to)
        eliminated_items = eliminated_items.filter(created_at__lte=date_to)
        quick_wins = quick_wins.filter(processed_at__lte=date_to)
    
    if category:
        tasks = tasks.filter(category=category)
        projects = projects.filter(category=category)
    
    if min_priority:
        min_priority = int(min_priority)
        tasks = tasks.filter(benefit__gte=F('cost') + min_priority)
        projects = projects.filter(benefit__gte=F('cost') + min_priority)
    
    # Handle export
    if export_format:
        if export_format == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="archives.csv"'
            writer = csv.writer(response)
            writer.writerow(['Type', 'Title/Text', 'Category', 'Added', 'Archived', 'Cost', 'Benefit', 'Score'])
            
            for task in tasks:
                writer.writerow(['Task', task.title, task.category, 
                               task.created_at.date(), task.archived_date.date(),
                               task.cost, task.benefit, task.efficiency_score])
            for project in projects:
                writer.writerow(['Project', project.title, project.category, 
                               project.created_at.date(), project.archived_date.date(),
                               project.cost, project.benefit, project.efficiency_score])
            for item in quick_wins:
                writer.writerow(['Quick Win', item.text, '', 
                               item.created_at.date(), item.processed_at.date(), '', '', ''])
            return response
            
        elif export_format == 'json':
            data = {
                'tasks': [{
                    'type': 'Task',
                    'title': task.title,
                    'category': task.category,
                    'added': task.created_at.isoformat(),
                    'archived': task.archived_date.isoformat(),
                    'cost': task.cost,
                    'benefit': task.benefit,
                    'score': task.efficiency_score
                } for task in tasks],
                'projects': [{
                    'type': 'Project',
                    'title': project.title,
                    'category': project.category,
                    'added': project.created_at.isoformat(),
                    'archived': project.archived_date.isoformat(),
                    'cost': project.cost,
                    'benefit': project.benefit,
                    'score': project.efficiency_score
                } for project in projects],
                'quick_wins': [{
                    'type': 'Quick Win',
                    'text': item.text,
                    'added': item.created_at.isoformat(),
                    'completed': item.processed_at.isoformat()
                } for item in quick_wins]
            }
            response = HttpResponse(json.dumps(data, indent=2), content_type='application/json')
            response['Content-Disposition'] = 'attachment; filename="archives.json"'
            return response
    
    # Get unique categories for filter dropdown
    categories = set(
        list(tasks.values_list('category', flat=True).distinct()) +
        list(projects.values_list('category', flat=True).distinct())
    )
    categories = [c for c in categories if c]  # Remove empty categories
    
    return render(request, 'gtd_app/archives.html', {
        'tasks': tasks.order_by('-archived_date'),
        'projects': projects.order_by('-archived_date'),
        'eliminated_items': eliminated_items.order_by('-processed_at'),
        'quick_wins': quick_wins.order_by('-processed_at'),
        'categories': sorted(categories),
        'filters': {
            'date_from': date_from,
            'date_to': date_to,
            'category': category,
            'min_priority': min_priority
        }
    })
