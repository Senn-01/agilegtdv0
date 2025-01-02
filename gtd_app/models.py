from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class InboxItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    eliminated = models.BooleanField(default=False)
    archive_category = models.CharField(max_length=50, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.processed and not self.processed_at:
            self.processed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.text[:50]}..."

class Sprint(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled')
        ],
        default='active'
    )
    
    class Meta:
        ordering = ['-start_date']
    
    def __str__(self):
        return f"Sprint {self.start_date.strftime('%Y-%m-%d')}"
    
    @property
    def is_active(self):
        return self.status == 'active'

class Task(models.Model):
    """Base abstract model for all task types"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, blank=True)
    benefit = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    cost = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    estimated_time = models.FloatField(
        default=1.0,
        help_text="Estimated time in weeks (0 for less than a week)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('todo', 'To Do'),
            ('in_progress', 'In Progress'),
            ('done', 'Done')
        ],
        default='todo'
    )
    sprint = models.ForeignKey(
        Sprint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    archived = models.BooleanField(default=False)
    archived_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        abstract = True
    
    def __str__(self):
        return self.title
    
    @property
    def efficiency_score(self):
        from .views import calculate_efficiency_score
        return calculate_efficiency_score(self.benefit, self.cost)

class SingleTask(Task):
    """A standalone task"""
    pass

class Project(Task):
    """A project that can contain multiple tasks"""
    pass

class ProjectTask(Task):
    """A task that belongs to a project"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    
    def save(self, *args, **kwargs):
        """Inherit project attributes if not explicitly set"""
        if not self.pk:  # Only for new tasks
            if not self.category:
                self.category = self.project.category
            if self.benefit == 5:  # Default value
                self.benefit = self.project.benefit
            if self.cost == 5:  # Default value
                self.cost = self.project.cost
            if self.estimated_time == 1.0:  # Default value
                self.estimated_time = self.project.estimated_time
        super().save(*args, **kwargs)

class Retrospective(models.Model):
    sprint = models.OneToOneField(Sprint, on_delete=models.CASCADE)
    total_tasks = models.IntegerField(default=0)
    completed_tasks = models.IntegerField(default=0)
    completion_rate = models.FloatField(default=0.0)
    average_efficiency = models.FloatField(default=0.0)
    achievements = models.TextField(blank=True)
    challenges = models.TextField(blank=True)
    action_items = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Retrospective for {self.sprint}"
