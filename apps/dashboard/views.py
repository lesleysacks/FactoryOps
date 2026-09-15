"""
FactoryOps Dashboard — Views

The dashboard is role-aware. Each role sees a different view of the system.
At this stage (Phase 1 foundation), a single placeholder home view is provided.
Role-specific dashboard content will be built in Phase 5.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """
    Factory operations home dashboard.
    Requires authentication — redirects to login if not authenticated.
    """
    context = {
        'user': request.user,
    }
    return render(request, 'dashboard/home.html', context)
