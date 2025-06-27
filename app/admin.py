from django.contrib import admin
from .models import (
    Tournament, TournamentRegistration, Team, UserProfile,
    TournamentBracket, BracketStage, BracketMatch,
    RoundRobinTable, RoundRobinResult, RoundRobinMatch
)

admin.site.register(Tournament)
admin.site.register(TournamentRegistration)
admin.site.register(Team)
admin.site.register(UserProfile)
admin.site.register(TournamentBracket)
admin.site.register(BracketStage)
admin.site.register(BracketMatch)
admin.site.register(RoundRobinTable)
admin.site.register(RoundRobinResult)
admin.site.register(RoundRobinMatch) 