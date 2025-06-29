#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#include <boost/test/unit_test.hpp>
#pragma GCC diagnostic pop

#include <sysio/chain/exceptions.hpp>
#include <sysio/chain/resource_limits.hpp>
#include <sysio/testing/tester.hpp>

#include <fc/exception/exception.hpp>
#include <fc/variant_object.hpp>

#include <contracts.hpp>

#include "sysio_system_tester.hpp"

/*
 * register test suite `ram_tests`
 */
BOOST_AUTO_TEST_SUITE(ram_tests)

/*************************************************************************************
 * ram_tests test case
 *************************************************************************************/
BOOST_FIXTURE_TEST_CASE(ram_tests, sysio_system::sysio_system_tester) { try {
   SKIP_TEST
   auto init_request_bytes = 80000 + 7110; // `7110' is for table token row
   const auto increment_contract_bytes = 10000;
   const auto table_allocation_bytes = 12000;
   BOOST_REQUIRE_MESSAGE(table_allocation_bytes > increment_contract_bytes, "increment_contract_bytes must be less than table_allocation_bytes for this test setup to work");
   buyrambytes(config::system_account_name, config::system_account_name, 70000);
   produce_blocks(10);
   create_account_with_resources("testram11111"_n,config::system_account_name, init_request_bytes + 40);
   create_account_with_resources("testram22222"_n,config::system_account_name, init_request_bytes + 1190);
   produce_blocks(10);
   BOOST_REQUIRE_EQUAL( success(), stake( name("sysio.stake"), name("testram11111"), core_from_string("10.0000"), core_from_string("5.0000") ) );
   produce_blocks(10);

   for (auto i = 0; i < 10; ++i) {
      try {
         set_code( "testram11111"_n, test_contracts::test_ram_limit_wasm() );
         break;
      } catch (const ram_usage_exceeded&) {
         init_request_bytes += increment_contract_bytes;
         buyrambytes(config::system_account_name, "testram11111"_n, increment_contract_bytes);
         buyrambytes(config::system_account_name, "testram22222"_n, increment_contract_bytes);
      }
   }
   produce_blocks(10);

   for (auto i = 0; i < 10; ++i) {
      try {
         set_abi( "testram11111"_n, test_contracts::test_ram_limit_abi() );
         break;
      } catch (const ram_usage_exceeded&) {
         init_request_bytes += increment_contract_bytes;
         buyrambytes(config::system_account_name, "testram11111"_n, increment_contract_bytes);
         buyrambytes(config::system_account_name, "testram22222"_n, increment_contract_bytes);
      }
   }
   produce_blocks(10);
   set_code( "testram22222"_n, test_contracts::test_ram_limit_wasm() );
   set_abi( "testram22222"_n, test_contracts::test_ram_limit_abi() );
   produce_blocks(10);

   auto total = get_total_stake( "testram11111"_n );
   const auto init_bytes =  total["ram_bytes"].as_uint64();

   auto rlm = control->get_resource_limits_manager();
   auto initial_ram_usage = rlm.get_account_ram_usage("testram11111"_n);

   // calculate how many more bytes we need to have table_allocation_bytes for database stores
   const long more_ram = table_allocation_bytes + init_bytes - init_request_bytes;
   BOOST_REQUIRE_MESSAGE(more_ram >= 0, "Underlying understanding changed, need to reduce size of init_request_bytes");
   wdump((init_bytes)(initial_ram_usage)(init_request_bytes)(more_ram) );
   buyrambytes(config::system_account_name, "testram11111"_n, more_ram);
   buyrambytes(config::system_account_name, "testram22222"_n, more_ram);

   validating_tester* tester = this;
   // allocate just under the allocated bytes
   tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                        ("payer", "testram11111")
                        ("from", 1)
                        ("to", 10)
                        ("size", 1780 /*1910*/));
   produce_blocks(1);
   auto ram_usage = rlm.get_account_ram_usage("testram11111"_n);

   total = get_total_stake( "testram11111"_n );
   const auto ram_bytes =  total["ram_bytes"].as_uint64();
   wdump((ram_bytes)(ram_usage)(initial_ram_usage)(init_bytes)(ram_usage - initial_ram_usage)(init_bytes - ram_usage) );

   wlog("ram_tests 1    %%%%%%");
   // allocate just beyond the allocated bytes
   BOOST_REQUIRE_EXCEPTION(
      tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                           ("payer", "testram11111")
                           ("from", 1)
                           ("to", 10)
                           ("size", 1920)),
                           ram_usage_exceeded,
                           fc_exception_message_starts_with("account testram11111 has insufficient ram"));
   wlog("ram_tests 2    %%%%%%");
   produce_blocks(1);
   BOOST_REQUIRE_EQUAL(ram_usage, rlm.get_account_ram_usage("testram11111"_n));

   // update the entries with smaller allocations so that we can verify space is freed and new allocations can be made
   tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                        ("payer", "testram11111")
                        ("from", 1)
                        ("to", 10)
                        ("size", 1680));
   produce_blocks(1);
   BOOST_REQUIRE_EQUAL(ram_usage - 1000, rlm.get_account_ram_usage("testram11111"_n));

   // verify the added entry is beyond the allocation bytes limit
   BOOST_REQUIRE_EXCEPTION(
      tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                           ("payer", "testram11111")
                           ("from", 1)
                           ("to", 11)
                           ("size", 1810)),
                           ram_usage_exceeded,
                           fc_exception_message_starts_with("account testram11111 has insufficient ram"));
   produce_blocks(1);
   BOOST_REQUIRE_EQUAL(ram_usage - 1000, rlm.get_account_ram_usage("testram11111"_n));

   // verify the new entry's bytes minus the freed up bytes for existing entries still exceeds the allocation bytes limit
   BOOST_REQUIRE_EXCEPTION(
      tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                           ("payer", "testram11111")
                           ("from", 1)
                           ("to", 11)
                           ("size", 1760)),
                           ram_usage_exceeded,
                           fc_exception_message_starts_with("account testram11111 has insufficient ram"));
   produce_blocks(1);
   BOOST_REQUIRE_EQUAL(ram_usage - 1000, rlm.get_account_ram_usage("testram11111"_n));

   // verify the new entry's bytes minus the freed up bytes for existing entries are under the allocation bytes limit
   tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                        ("payer", "testram11111")
                        ("from", 1)
                        ("to", 11)
                        ("size", 1720));
   produce_blocks(1);

   tester->push_action( "testram11111"_n, "rmentry"_n, "testram11111"_n, mvo()
                        ("from", 3)
                        ("to", 3));
   produce_blocks(1);
   
   // verify that the new entry will exceed the allocation bytes limit
   BOOST_REQUIRE_EXCEPTION(
      tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                           ("payer", "testram11111")
                           ("from", 12)
                           ("to", 12)
                           ("size", 1780)),
                           ram_usage_exceeded,
                           fc_exception_message_starts_with("account testram11111 has insufficient ram"));
   produce_blocks(1);

   // verify that the new entry is under the allocation bytes limit
   tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                        ("payer", "testram11111")
                        ("from", 12)
                        ("to", 12)
                        ("size", 1720));
   produce_blocks(1);

   // verify that anoth new entry will exceed the allocation bytes limit, to setup testing of new payer
   BOOST_REQUIRE_EXCEPTION(
      tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                           ("payer", "testram11111")
                           ("from", 13)
                           ("to", 13)
                           ("size", 1660)),
                           ram_usage_exceeded,
                           fc_exception_message_starts_with("account testram11111 has insufficient ram"));
   produce_blocks(1);

   // verify that the new entry is under the allocation bytes limit
   tester->push_action( "testram11111"_n, "setentry"_n, {"testram11111"_n,"testram22222"_n}, mvo()
                        ("payer", "testram22222")
                        ("from", 12)
                        ("to", 12)
                        ("size", 1720));
   produce_blocks(1);

   // verify that another new entry that is too big will exceed the allocation bytes limit, to setup testing of new payer
   BOOST_REQUIRE_EXCEPTION(
      tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                           ("payer", "testram11111")
                           ("from", 13)
                           ("to", 13)
                           ("size", 1900)),
                           ram_usage_exceeded,
                           fc_exception_message_starts_with("account testram11111 has insufficient ram"));
   produce_blocks(1);

   wlog("ram_tests 18    %%%%%%");
   // verify that the new entry is under the allocation bytes limit, because entry 12 is now charged to testram22222
   tester->push_action( "testram11111"_n, "setentry"_n, "testram11111"_n, mvo()
                        ("payer", "testram11111")
                        ("from", 13)
                        ("to", 13)
                        ("size", 1720));
   produce_blocks(1);

   wlog("ram_tests 19    %%%%%%");
   // verify that new entries for testram22222 exceed the allocation bytes limit
   BOOST_REQUIRE_EXCEPTION(
      tester->push_action( "testram11111"_n, "setentry"_n, {"testram11111"_n,"testram22222"_n}, mvo()
                           ("payer", "testram22222")
                           ("from", 12)
                           ("to", 21)
                           ("size", 2040)),
                           ram_usage_exceeded,
                           fc_exception_message_starts_with("account testram22222 has insufficient ram"));
   produce_blocks(1);

   wlog("ram_tests 20    %%%%%%");
   // verify that new entries for testram22222 are under the allocation bytes limit
   tester->push_action( "testram11111"_n, "setentry"_n, {"testram11111"_n,"testram22222"_n}, mvo()
                        ("payer", "testram22222")
                        ("from", 12)
                        ("to", 21)
                        ("size", 2020));
   produce_blocks(1);

   // verify that new entry for testram22222 exceed the allocation bytes limit
   BOOST_REQUIRE_EXCEPTION(
      tester->push_action( "testram11111"_n, "setentry"_n, {"testram11111"_n,"testram22222"_n}, mvo()
                           ("payer", "testram22222")
                           ("from", 22)
                           ("to", 22)
                           ("size", 2020)),
                           ram_usage_exceeded,
                           fc_exception_message_starts_with("account testram22222 has insufficient ram"));
   produce_blocks(1);

   tester->push_action( "testram11111"_n, "rmentry"_n, "testram11111"_n, mvo()
                        ("from", 20)
                        ("to", 20));
   produce_blocks(1);

   // verify that new entry for testram22222 are under the allocation bytes limit
   tester->push_action( "testram11111"_n, "setentry"_n, {"testram11111"_n,"testram22222"_n}, mvo()
                        ("payer", "testram22222")
                        ("from", 22)
                        ("to", 22)
                        ("size", 1910));
   produce_blocks(1);

} FC_LOG_AND_RETHROW() }

BOOST_AUTO_TEST_SUITE_END()
