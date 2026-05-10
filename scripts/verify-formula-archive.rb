#!/usr/bin/env ruby
# frozen_string_literal: true

# Verify that Formula/gitig.rb's tarball url matches its sha256 line.
# Usage: ARCHIVE_PATH=/tmp/t.tgz scripts/verify-formula-archive.rb [path-to-formula.rb]

require "digest"
require "tempfile"

path = ARGV[0] || "Formula/gitig.rb"
s = File.read(path)

url = s[/^\s*url\s+"([^"]+)"/, 1]
abort "could not parse url from #{path}" unless url
expected = s[/^\s*sha256\s+"([^"]+)"/, 1]
abort "could not parse sha256 from #{path}" unless expected

abort "REPLACE_ME in #{path}: set a real checksum (see scripts/write-gitig-formula-sha.sh)" if expected == "REPLACE_ME"

abort "checksum must be 64 hex chars" unless expected.match?(/\A[a-f0-9]{64}\z/)

archive = ENV["ARCHIVE_PATH"]
unlink = false

if archive.nil? || archive.strip.empty?
  t = Tempfile.new(%w[gitig-archive .tar.gz])
  t.close
  archive = t.path
  unlink = true
end

system("curl", "--fail", "--silent", "--show-error", "--location", "--output", archive, url) || abort("curl failed")
actual = Digest::SHA256.file(archive).hexdigest
File.unlink(archive) if unlink

unless actual == expected
  abort("checksum mismatch:\n expected #{expected}\n actual   #{actual}")
end

puts "OK  #{actual}  #{url}"
