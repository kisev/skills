# Provision only harness-owned identities. Credentials leave the container on stdin/stdout,
# never in Docker command arguments or committed files.
require 'json'
input = JSON.parse(STDIN.read)
result = { 'users' => {}, 'groups' => {} }
roles = %w[author reviewer outsider]
roles << 'manual' if input.fetch('initialize_manual', false)
roles.each do |role|
  username = "gt-#{input.fetch('owner')}-#{role}"
  existing = User.find_by_username(username)
  password = input.fetch('users').fetch(role).fetch('password')
  user = existing || User.new(
    username: username, name: "Harness #{role}",
    email: "#{username}@example.invalid", password: password,
    password_confirmation: password
  )
  user.skip_confirmation!
  user.password = user.password_confirmation = password if role == 'manual'
  user.assign_personal_namespace(Organizations::Organization.default_organization)
  user.save!
  Organizations::OrganizationUser.update_home_organization_record_for(user, user_is_admin: false)
  token_value = input.fetch('users').fetch(role).fetch('token')
  token = user.personal_access_tokens.find_by(name: 'gitlab-test')
  unless token
    token = user.personal_access_tokens.build(
      name: 'gitlab-test', scopes: ['api'], expires_at: 30.days.from_now.to_date
    )
    token.set_token(token_value)
    token.save!
  end
  if token.expires_at <= Date.today
    token.update!(expires_at: 30.days.from_now.to_date)
  end
  if role == 'manual'
    token.set_token(token_value)
    token.save!
  end
  result['users'][role] = { 'id' => user.id, 'username' => username }
end
author = User.find(result.fetch('users').fetch('author').fetch('id'))
reviewer = User.find(result.fetch('users').fetch('reviewer').fetch('id'))
group_path = "gt-#{input.fetch('owner')}-fixtures"
group = Group.find_by_full_path(group_path)
unless group
  response = Groups::CreateService.new(author, name: 'fixtures', path: group_path, visibility_level: 0, organization_id: Organizations::Organization.default_organization.id).execute
  group = response[:group]
  raise "Fixture group creation failed: #{group&.errors&.full_messages}" unless group&.persisted?
end
group.add_owner(author) unless group.member?(author)
group.add_maintainer(reviewer) unless group.member?(reviewer)
result['groups']['fixtures'] = { 'id' => group.id, 'path' => group.full_path }
if input.fetch('initialize_manual', false)
  manual_user = User.find(result.fetch('users').fetch('manual').fetch('id'))
  manual_group = Group.find_by_full_path("gt-#{input.fetch('owner')}-manual-group")
  unless manual_group
    response = Groups::CreateService.new(manual_user, name: 'manual', path: "gt-#{input.fetch('owner')}-manual-group", visibility_level: 0, organization_id: Organizations::Organization.default_organization.id).execute
    manual_group = response[:group]
    raise "Manual group creation failed: #{manual_group&.errors&.full_messages}" unless manual_group&.persisted?
  end
  result['groups']['manual'] = { 'id' => manual_group.id, 'path' => manual_group.full_path }
end
puts "HARNESS_JSON=#{JSON.generate(result)}"
