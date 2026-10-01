# Provision only harness-owned identities. Credentials leave the container on stdin/stdout,
# never in Docker command arguments or committed files.
require 'json'
input = JSON.parse(STDIN.read)
result = { 'users' => {} }
%w[author reviewer outsider].each do |role|
  username = "gt-#{input.fetch('owner')}-#{role}"
  existing = User.find_by_username(username)
  password = input.fetch('users').fetch(role).fetch('password')
  user = existing || User.new(
    username: username, name: "Harness #{role}",
    email: "#{username}@example.invalid", password: password,
    password_confirmation: password
  )
  user.skip_confirmation!
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
  result['users'][role] = { 'id' => user.id, 'username' => username }
end
puts "HARNESS_JSON=#{JSON.generate(result)}"
